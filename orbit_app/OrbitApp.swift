import PDFKit
import SwiftUI
import AppKit
@preconcurrency import WebKit
import UniformTypeIdentifiers
import AVFoundation

/// A packaged copy for another Mac carries its backend and puts it in place at first start. The owner's installed app has no bundled core: nothing happens there.
enum FirstRun {
    static func prepare() {
        let manager = FileManager.default
        guard let bundled = Bundle.main.resourceURL?.appendingPathComponent("core"), manager.fileExists(atPath: bundled.path) else { return }
        let core = manager.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Orbit/core"), stamp = core.appendingPathComponent(".bundle-version")
        let version = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? ""
        if (try? String(contentsOf: stamp, encoding: .utf8)) != version {
            try? manager.createDirectory(at: core, withIntermediateDirectories: true)
            for item in (try? manager.contentsOfDirectory(at: bundled, includingPropertiesForKeys: nil)) ?? [] {
                let target = core.appendingPathComponent(item.lastPathComponent)
                try? manager.removeItem(at: target); try? manager.copyItem(at: item, to: target)
            }
            try? version.write(to: stamp, atomically: true, encoding: .utf8)
        }
        // The backend needs Apple's own Python, which comes with the free Command Line Tools.
        let check = Process(); check.executableURL = URL(fileURLWithPath: "/usr/bin/xcode-select"); check.arguments = ["-p"]
        check.standardOutput = FileHandle.nullDevice; check.standardError = FileHandle.nullDevice
        try? check.run(); check.waitUntilExit()
        if check.terminationStatus != 0 {
            let install = Process(); install.executableURL = URL(fileURLWithPath: "/usr/bin/xcode-select"); install.arguments = ["--install"]; try? install.run()
            let alert = NSAlert(); alert.messageText = "Még egy dolog kell az ORBIT-nak"; alert.informativeText = "Telepítsd az Apple ingyenes Command Line Tools csomagját a megjelenő ablakban, majd indítsd újra az ORBIT-ot."; alert.runModal()
        }
    }
}

final class OrbitChatWebView: WKWebView {
    var onFilesDropped: (([URL], CGPoint) -> Void)?
    private var lastHover: TimeInterval = 0
    private func files(_ sender: NSDraggingInfo) -> [URL] {
        (sender.draggingPasteboard.readObjects(forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true]) as? [URL]) ?? []
    }
    private func point(_ sender: NSDraggingInfo) -> CGPoint {
        let p = convert(sender.draggingLocation, from: nil)
        return CGPoint(x: p.x, y: isFlipped ? p.y : bounds.height - p.y)
    }
    override func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation {
        guard !files(sender).isEmpty else { return super.draggingEntered(sender) }
        let p = point(sender); evaluateJavaScript("window.orbitDropHover?.(\(p.x),\(p.y))", completionHandler: nil)
        return .copy
    }
    override func draggingUpdated(_ sender: NSDraggingInfo) -> NSDragOperation {
        guard !files(sender).isEmpty else { return super.draggingUpdated(sender) }
        if Date.timeIntervalSinceReferenceDate - lastHover > 0.05 {
            lastHover = Date.timeIntervalSinceReferenceDate
            let p = point(sender); evaluateJavaScript("window.orbitDropHover?.(\(p.x),\(p.y))", completionHandler: nil)
        }
        return .copy
    }
    override func draggingExited(_ sender: NSDraggingInfo?) {
        evaluateJavaScript("window.orbitDropLeave?.()", completionHandler: nil)
        super.draggingExited(sender)
    }
    override func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
        let urls = files(sender)
        guard !urls.isEmpty else { return super.performDragOperation(sender) }
        onFilesDropped?(urls, point(sender)); return true
    }
}

struct OrbitSurface: NSViewRepresentable {
    func makeCoordinator() -> Coordinator { Coordinator() }
    func makeNSView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.setURLSchemeHandler(OrbitMediaHandler(), forURLScheme: "orbit-media")
        configuration.userContentController.add(context.coordinator, name: "orbit")
        let web = OrbitChatWebView(frame: .zero, configuration: configuration)
        web.registerForDraggedTypes([.fileURL])
        web.onFilesDropped = { [weak coordinator = context.coordinator] urls, point in coordinator?.receiveFiles(urls, point: point) }
        web.navigationDelegate = context.coordinator
        web.uiDelegate = context.coordinator
        web.setValue(false, forKey: "drawsBackground")
        context.coordinator.web = web
        FirstRun.prepare()
        context.coordinator.startVideoLane()
        if let folder = Bundle.main.resourceURL?.appendingPathComponent("Studio") {
            web.loadFileURL(folder.appendingPathComponent("index.html"), allowingReadAccessTo: folder)
        }
        return web
    }
    func updateNSView(_ view: WKWebView, context: Context) {}

    final class Coordinator: NSObject, WKScriptMessageHandler, WKNavigationDelegate, WKUIDelegate, AVAudioPlayerDelegate {
        weak var web: WKWebView?
        var recorder: AVAudioRecorder?
        var player: AVAudioPlayer?
        var speakingId: String?
        var speakingEngine = ""
        private var videoLane: Process?
        private var droppedFiles: [String: (url: URL, expires: Date)] = [:]
        private struct Upload {
            let url: URL, handle: FileHandle, project: String, size: Int
            var received: Int = 0
            let expires = Date().addingTimeInterval(600)
        }
        private var uploads: [String: Upload] = [:]
        deinit {
            for upload in uploads.values {
                try? upload.handle.close(); try? FileManager.default.removeItem(at:upload.url.deletingLastPathComponent())
            }
        }

        private func discardUpload(_ token: String) {
            if let upload = uploads.removeValue(forKey: token) {
                try? upload.handle.close(); try? FileManager.default.removeItem(at: upload.url.deletingLastPathComponent())
            }
        }

        private func uploadRequest(_ id: String, _ action: String, _ request: [String: Any]) {
            for token in Array(uploads.keys) where uploads[token]!.expires < Date() { discardUpload(token) }
            do {
                if action == "command_file_begin" {
                    guard uploads.count < 8, let size = request["size"] as? Int, size > 0, size <= 2 * 1024 * 1024 * 1024,
                          let name = request["name"] as? String, let project = request["project"] as? String else {
                        reply(id,["ok":false,"message":"Legfeljebb 8 fájl, egyenként 2 GB csatolható."]); return
                    }
                    let filename = URL(fileURLWithPath: name).lastPathComponent
                    guard !filename.isEmpty, filename != ".", filename != "..", filename.utf8.count <= 240 else { reply(id,["ok":false,"message":"Érvénytelen fájlnév."]); return }
                    let free = try FileManager.default.attributesOfFileSystem(forPath: NSTemporaryDirectory())[.systemFreeSize] as? NSNumber
                    guard let free, free.int64Value - Int64(size) > 512 * 1024 * 1024 else { reply(id,["ok":false,"message":"Nincs elegendő szabad tárhely a csatoláshoz."]); return }
                    let token = UUID().uuidString
                    let folder = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("ORBIT-chat-uploads").appendingPathComponent(token)
                    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true, attributes: [.posixPermissions:0o700])
                    let url = folder.appendingPathComponent(filename)
                    guard FileManager.default.createFile(atPath: url.path, contents: nil, attributes: [.posixPermissions:0o600]) else { throw NSError(domain:"ORBIT",code:9) }
                    uploads[token] = Upload(url:url,handle:try FileHandle(forWritingTo:url),project:project,size:size)
                    reply(id,["ok":true,"token":token]); return
                }
                guard let token = request["token"] as? String, var upload = uploads[token], upload.project == request["project"] as? String else {
                    reply(id,["ok":false,"message":"A csatolási munkamenet lejárt."]); return
                }
                if action == "command_file_abort" { discardUpload(token); reply(id,["ok":true]); return }
                if action == "command_file_chunk" {
                    guard let offset = request["offset"] as? Int, offset == upload.received,
                          let encoded = request["data"] as? String, encoded.count <= 1024 * 1024,
                          let data = Data(base64Encoded:encoded), !data.isEmpty, upload.received + data.count <= upload.size else {
                        discardUpload(token); reply(id,["ok":false,"message":"Hiányos fájlrészlet. Húzd ide újra a fájlt."]); return
                    }
                    try upload.handle.write(contentsOf:data); upload.received += data.count; uploads[token] = upload
                    reply(id,["ok":true,"received":upload.received]); return
                }
                guard action == "command_file_end", upload.received == upload.size else {
                    discardUpload(token); reply(id,["ok":false,"message":"A fájl nem érkezett meg teljesen."]); return
                }
                try upload.handle.close(); uploads.removeValue(forKey:token)
                importChatFile(id,request:request,url:upload.url,temporaryFolder:upload.url.deletingLastPathComponent())
            } catch {
                if let token = request["token"] as? String { discardUpload(token) }
                reply(id,["ok":false,"message":error.localizedDescription])
            }
        }

        func receiveFiles(_ urls: [URL], point: CGPoint) {
            droppedFiles = droppedFiles.filter { $0.value.expires > Date() }
            guard urls.count <= 8 else { web?.evaluateJavaScript("toast('Egyszerre legfeljebb 8 fájlt csatolj.',true)", completionHandler: nil); return }
            let items: [[String: String]] = urls.map { url in
                let token = UUID().uuidString
                droppedFiles[token] = (url, Date().addingTimeInterval(600))
                return ["token": token, "label": url.lastPathComponent]
            }
            guard let raw = try? JSONSerialization.data(withJSONObject: items), let encoded = String(data: raw, encoding: .utf8) else { return }
            web?.evaluateJavaScript("window.orbitReceiveDroppedFiles?.(\(encoded),\(point.x),\(point.y))", completionHandler: nil)
        }

        func importChatFile(_ id: String, request: [String: Any], url: URL, temporaryFolder: URL? = nil) {
            DispatchQueue.global(qos: .userInitiated).async { [weak self] in
                var revised = request
                revised["action"] = "import_media"; revised["source"] = url.path; revised["chat_attachment"] = true
                if url.pathExtension.lowercased() == "pdf",
                   let size = try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize, size <= 64 * 1024 * 1024,
                   let document = PDFDocument(url: url), !document.isLocked {
                    var text = ""
                    for i in 0..<min(document.pageCount, 160) {
                        guard text.count < 200_000 else { break }
                        if let page = document.page(at: i)?.string { text += "\n[Page \(i + 1)]\n" + String(page.prefix(max(0, 200_000 - text.count))) }
                    }
                    revised["pdf_text"] = text
                }
                self?.perform(id, revised, cleanup: temporaryFolder)
            }
        }

        func startVideoLane() {
            guard videoLane == nil else { return }
            let script = FileManager.default.homeDirectoryForCurrentUser
                .appendingPathComponent("Library/Application Support/Orbit/core/local_video.py")
            guard FileManager.default.fileExists(atPath: script.path) else { return }
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
            process.arguments = [script.path]
            process.standardInput = FileHandle.nullDevice
            process.standardOutput = FileHandle.nullDevice
            process.standardError = FileHandle.nullDevice
            var environment = ProcessInfo.processInfo.environment
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            process.environment = environment
            do {
                try process.run()
                videoLane = process
            } catch {
                NSLog("ORBIT: the local video lane could not start: %@", error.localizedDescription)
            }
        }
        func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
            guard player === self.player, let id = speakingId else { return }
            speakingId = nil; reply(id, ["ok": true, "engine": speakingEngine])
        }
        private let actions: Set<String> = ["venture_folder", "venture_try", "voice_status", "enterprise_status", "enterprise_save", "mission_list", "mission_save", "mission_start", "mission_pause", "mission_resume", "editing_review", "editing_feedback", "editing_preferences", "editing_revise", "model_evaluation_status", "model_evaluation_start", "app_status", "project_role_save", "production_resume", "growth_list", "growth_save", "growth_refresh", "growth_produce", "publication_list", "publication_approve", "publication_settings", "command_continue", "automation_tasks", "automation_context", "automation_toggle", "automation_list", "automation_save", "automation_run", "automation_stop", "telegram_status", "telegram_pair", "telegram_unpair", "connections_agents_auto", "connections_status", "connections_save", "connections_test", "command_retry_agent", "command_overview", "command_memory_save", "command_memory_forget", "command_preferences_save", "command_state", "command_send", "command_approve", "command_reject", "command_revoke", "model_hub", "room_save", "room_archive", "room_restore", "connection_save", "connection_archive", "graph_run", "ensure", "snapshot", "models", "engines", "project_create", "project_save", "agent_save", "chat", "agent_run", "job_cancel", "pipeline", "recipe_save", "recipe_run", "model_pull", "workflow_save", "media_generate", "artifact_preview", "media_analyze", "job_detail", "youtube_status", "youtube_connect", "youtube_disconnect", "youtube_upload", "short_start", "short_automation_save", "short_cancel", "gallery_list", "project_app"]
        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            // Only the bundled interface may load. Generated content never enters this origin.
            // A generated app runs in the chat's preview frame only: from orbit-media, sandboxed, with no network and no bridge.
            if navigationAction.targetFrame?.isMainFrame == false, navigationAction.request.url?.scheme == "orbit-media" { decisionHandler(.allow); return }
            if let url = navigationAction.request.url, let base = Bundle.main.resourceURL?.appendingPathComponent("Studio").path,
               url.isFileURL, url.standardizedFileURL.path.hasPrefix(base + "/"), navigationAction.navigationType != .linkActivated {
                decisionHandler(.allow)
            } else { decisionHandler(.cancel) }
        }
        func reply(_ id: String, _ result: [String: Any]) {
            var value = result; value["requestId"] = id
            guard let data = try? JSONSerialization.data(withJSONObject: value, options: [.fragmentsAllowed]), let encoded = String(data: data, encoding: .utf8) else { return }
            DispatchQueue.main.async { [weak self] in self?.web?.evaluateJavaScript("window.resolveNative(\(encoded))", completionHandler: nil) }
        }
        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            guard message.frameInfo.isMainFrame, let request = message.body as? [String: Any], let id = request["requestId"] as? String,
                  let action = request["action"] as? String else { return }
            if ["command_file_begin","command_file_chunk","command_file_end","command_file_abort"].contains(action) {
                uploadRequest(id,action,request); return
            }
            if action == "open_youtube" {
                guard let video = request["video"] as? String,
                      video.range(of: "^[A-Za-z0-9_-]{11}$", options: .regularExpression) != nil else { reply(id,["ok":false,"message":"Érvénytelen YouTube-videóazonosító."]); return }
                let address = request["studio"] as? Bool == true ? "https://studio.youtube.com/video/\(video)/edit" : "https://www.youtube.com/watch?v=\(video)"
                guard let url = URL(string: address) else { return }
                NSWorkspace.shared.open(url); reply(id,["ok":true]); return
            }
            if action == "connection_signup" {
                let links = ["deepseek":"https://platform.deepseek.com/api_keys", "etsy":"https://www.etsy.com/developers/your-apps", "groq":"https://console.groq.com/keys", "openrouter":"https://openrouter.ai/settings/keys", "gemini":"https://aistudio.google.com/api-keys", "tavily":"https://app.tavily.com/", "jina":"https://jina.ai/reader/", "telegram":"https://t.me/BotFather"]
                guard let provider = request["provider"] as? String, let address = links[provider], let url = URL(string: address) else { reply(id,["ok":false,"message":"Ismeretlen szolgáltató."]); return }
                NSWorkspace.shared.open(url); reply(id,["ok":true]); return
            }
            if action == "models_pick_folder" {
                // Only reads the chosen folder for models: unlike command_pick_folder it grants the assistant nothing.
                let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = false; panel.allowsMultipleSelection = false
                panel.message = "Válaszd ki a mappát, ahol a meglévő AI modelljeid vannak (Ollama-modellmappa vagy .gguf fájlok)."
                panel.begin { [weak self] result in
                    guard let self else { return }
                    guard result == .OK, let url = panel.url else { self.reply(id, ["ok": true, "cancelled": true]); return }
                    var revised = request; revised["action"] = "project_app"; revised["op"] = "locator_use"; revised["args"] = ["path": url.path]; self.perform(id, revised)
                }
                return
            }
            if action == "command_pick_folder" {
                let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = false; panel.allowsMultipleSelection = false
                panel.message = "Ehhez a mappához és almappáihoz olvasást és jóváhagyott szerkesztést engedélyezel a fő asszisztensnek."
                panel.begin { [weak self] result in
                    guard let self else { return }
                    guard result == .OK, let url = panel.url else { self.reply(id, ["ok": true, "cancelled": true]); return }
                    var revised = request; revised["action"] = "command_grant"; revised["path"] = url.path; self.perform(id, revised)
                }
                return
            }
            if action == "command_pick_image" {
                let panel = NSOpenPanel(); panel.canChooseDirectories = false; panel.allowsMultipleSelection = false
                panel.message = "Csatolj képet, videót, hangot vagy dokumentumot (fájlonként legfeljebb 2 GB)."
                panel.begin { [weak self] result in
                    guard let self else { return }
                    guard result == .OK, let url = panel.url else { self.reply(id, ["ok": true, "cancelled": true]); return }
                    self.importChatFile(id, request: request, url: url)
                }
                return
            }
            if action == "command_import_drop" {
                guard let token = request["token"] as? String, let selected = droppedFiles.removeValue(forKey: token), selected.expires > Date() else {
                    reply(id, ["ok": false, "message": "A csatoláshoz húzd ide újra a fájlt."]); return
                }
                importChatFile(id, request: request, url: selected.url); return
            }
            if action == "import_media_file" {
                let panel = NSOpenPanel(); panel.canChooseDirectories = false; panel.allowsMultipleSelection = false
                panel.allowedContentTypes = [.movie, .audio, .image]
                panel.message = "Videó, hang vagy kép hozzáadása a projekthez (legfeljebb 2 GB)."
                panel.begin { [weak self] result in
                    guard let self else { return }
                    guard result == .OK, let url = panel.url else { self.reply(id, ["ok": true, "cancelled": true]); return }
                    var imported = request; imported["action"] = "import_media"; imported["source"] = url.path
                    self.perform(id, imported)
                }
                return
            }
            if action == "pick_json" || action == "import_project_file" || action == "import_youtube_config" {
                let panel = NSOpenPanel(); panel.canChooseDirectories = false; panel.allowsMultipleSelection = false
                panel.allowedContentTypes = action != "import_project_file" ? [.json] : [.text, .json, .sourceCode, .commaSeparatedText, .xml, .svg]
                panel.message = action == "pick_json" ? "Válassz ComfyUI API formátumú munkafolyamatot." : action == "import_youtube_config" ? "Válaszd ki a Google Cloud Desktop app OAuth JSON-fájlját. Ez elkülönített beállításként tárolódik." : "A kiválasztott szöveges fájl másolata a projektbe kerül."
                panel.begin { [weak self] result in
                    guard let self else { return }
                    guard result == .OK, let url = panel.url else { self.reply(id, ["ok": true, "cancelled": true, "content": ""]); return }
                    do {
                        let info = try url.resourceValues(forKeys: [.fileSizeKey]); let limit = action == "pick_json" ? 2*1024*1024 : 1024*1024
                        guard (info.fileSize ?? Int.max) <= limit else { throw NSError(domain: "ORBIT", code: 1, userInfo: [NSLocalizedDescriptionKey: "A fájl túl nagy."]) }
                        let data = try Data(contentsOf: url)
                        guard let content = String(data: data, encoding: .utf8) else { throw NSError(domain: "ORBIT", code: 2, userInfo: [NSLocalizedDescriptionKey: "UTF-8 szöveges fájl szükséges."]) }
                        if action == "pick_json" { self.reply(id, ["ok": true, "content": content, "name": url.lastPathComponent]) }
                        else if action == "import_youtube_config" {
                            var imported = request; imported["action"] = "youtube_config"; imported["content"] = content; self.perform(id, imported)
                        } else {
                            var imported = request; imported["action"] = "import_file"; imported["name"] = url.lastPathComponent; imported["data"] = data.base64EncodedString()
                            self.perform(id, imported)
                        }
                    } catch { self.reply(id, ["ok": false, "message": error.localizedDescription]) }
                }
                return
            }
            if action == "voice_listen_start" {
                // Native recording: the bundled file:// page cannot rely on getUserMedia.
                AVCaptureDevice.requestAccess(for: .audio) { [weak self] granted in
                    guard let self else { return }
                    guard granted else { self.reply(id, ["ok": false, "message": "Az ORBIT nem kapott mikrofon-engedélyt (Rendszerbeállítások → Adatvédelem → Mikrofon)."]); return }
                    DispatchQueue.main.async {
                        let folder = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Orbit/voice")
                        try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
                        let url = folder.appendingPathComponent("rec-\(UUID().uuidString).m4a")
                        let settings: [String: Any] = [AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: 16000, AVNumberOfChannelsKey: 1, AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue]
                        do {
                            self.recorder?.stop()
                            let recorder = try AVAudioRecorder(url: url, settings: settings); recorder.isMeteringEnabled = true
                            guard recorder.record(forDuration: 120) else { throw NSError(domain: "ORBIT", code: 5) }
                            self.recorder = recorder; self.reply(id, ["ok": true])
                        } catch { self.reply(id, ["ok": false, "message": "A mikrofon nem indítható el."]) }
                    }
                }
                return
            }
            if action == "voice_level" {
                guard let recorder, recorder.isRecording else { reply(id, ["ok": true, "recording": false]); return }
                recorder.updateMeters(); reply(id, ["ok": true, "recording": true, "level": Double(recorder.averagePower(forChannel: 0)), "seconds": recorder.currentTime]); return
            }
            if action == "voice_listen_stop" {
                guard let recorder else { reply(id, ["ok": false, "message": "Nincs folyamatban felvétel."]); return }
                let url = recorder.url, seconds = recorder.currentTime; recorder.stop(); self.recorder = nil
                if request["cancel"] as? Bool == true || seconds < 0.4 { try? FileManager.default.removeItem(at: url); reply(id, ["ok": true, "text": "", "cancelled": true]); return }
                var revised = request; revised["action"] = "voice_transcribe"; revised["path"] = url.path
                perform(id, revised); return
            }
            if action == "voice_speak" {
                // The answer is synthesised by the core, played here; the reply arrives when speech ends.
                var revised = request; revised["action"] = "voice_speak"
                perform(id, revised, playVoice: true); return
            }
            if action == "voice_stop_speaking" {
                player?.stop(); if let pending = speakingId { speakingId = nil; reply(pending, ["ok": true, "stopped": true]) }
                reply(id, ["ok": true]); return
            }
            if action == "open_artifact" {
                var revised = request; revised["action"] = "artifact"
                perform(id, revised, openArtifact: true); return
            }
            guard actions.contains(action) else { reply(id, ["ok": false, "message": "Ismeretlen művelet."]); return }
            perform(id, request)
        }
        private func perform(_ id: String, _ request: [String: Any], openArtifact: Bool = false, playVoice: Bool = false, cleanup: URL? = nil) {
            DispatchQueue.global(qos: .userInitiated).async { [weak self] in
                defer { if let cleanup { try? FileManager.default.removeItem(at:cleanup) } }
                do {
                    let root = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Orbit/core")
                    let process = Process(); process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
                    let foregroundDownload = request["action"] as? String == "project_app" && request["op"] as? String == "finder_generation_pull"
                    process.arguments = [root.appendingPathComponent("bridge.py").path] + (foregroundDownload ? ["--foreground-generation"] : [])
                    process.currentDirectoryURL = root
                    var environment = ProcessInfo.processInfo.environment; environment["PYTHONDONTWRITEBYTECODE"] = "1"; process.environment = environment
                    let input = Pipe(), output = Pipe(); process.standardInput = input; process.standardOutput = output; process.standardError = FileHandle.nullDevice
                    try process.run()
                    try input.fileHandleForWriting.write(contentsOf: JSONSerialization.data(withJSONObject: request)); try input.fileHandleForWriting.close()
                    let data = output.fileHandleForReading.readDataToEndOfFile()
                    if !foregroundDownload { process.waitUntilExit() }
                    guard foregroundDownload || process.terminationStatus == 0,
                          let response = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                        throw NSError(domain: "ORBIT", code: 3, userInfo: [NSLocalizedDescriptionKey: "A helyi műhelykapcsolat nem válaszolt."])
                    }
                    if foregroundDownload {
                        // The downloader closes its reply pipe after registering the job. Progress comes from the model library.
                        self?.reply(id, response)
                        process.waitUntilExit()
                        return
                    }
                    if request["action"] as? String == "telegram_pair", response["ok"] as? Bool == true, let address = response["url"] as? String, let url = URL(string: address), url.scheme == "https", url.host == "t.me" {
                        DispatchQueue.main.async { NSWorkspace.shared.open(url) }
                    }
                    if request["action"] as? String == "youtube_connect", response["ok"] as? Bool == true, let address = response["auth_url"] as? String, let url = URL(string: address), url.scheme == "https", url.host == "accounts.google.com" {
                        DispatchQueue.main.async { NSWorkspace.shared.open(url); self?.reply(id, ["ok": true]) }
                    } else if playVoice, response["ok"] as? Bool == true, let path = response["path"] as? String,
                              path.hasPrefix(FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Orbit/voice").path + "/") {
                        DispatchQueue.main.async {
                            guard let self else { return }
                            self.player?.stop(); if let pending = self.speakingId { self.reply(pending, ["ok": true, "stopped": true]) }
                            guard let player = try? AVAudioPlayer(contentsOf: URL(fileURLWithPath: path)) else { self.reply(id, ["ok": false, "message": "A hang nem játszható le."]); return }
                            player.delegate = self; self.player = player; self.speakingId = id; self.speakingEngine = response["engine"] as? String ?? ""
                            player.play()
                        }
                    } else if openArtifact, response["ok"] as? Bool == true, let path = response["path"] as? String {
                        DispatchQueue.main.async {
                            let opened = NSWorkspace.shared.open(URL(fileURLWithPath: path))
                            self?.reply(id, ["ok": opened, "message": opened ? "Megnyitva." : "A fájl nem nyitható meg."])
                        }
                    } else { self?.reply(id, response) }
                } catch { self?.reply(id, ["ok": false, "message": error.localizedDescription]) }
            }
        }
    }
}

@main struct OrbitApp: App {
    @NSApplicationDelegateAdaptor(ApplicationDelegate.self) var delegate
    var body: some Scene {
        WindowGroup("ORBIT") {
            OrbitSurface().background(Color(red: 0.067, green: 0.098, blue: 0.114)).frame(minWidth: 700, minHeight: 650)
        }.defaultSize(width: 1440, height: 940).windowStyle(.hiddenTitleBar)
        .commands { CommandGroup(replacing: .newItem) {} }
    }
}
