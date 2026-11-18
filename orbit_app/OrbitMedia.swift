import Foundation
@preconcurrency import WebKit
import UniformTypeIdentifiers

/// Project-validated local media, including range requests for inline video playback.
final class OrbitMediaHandler: NSObject, WKURLSchemeHandler {
    private var active = Set<ObjectIdentifier>()
    private let lock = NSLock()
    private func isActive(_ key: ObjectIdentifier) -> Bool { lock.lock(); defer { lock.unlock() }; return active.contains(key) }
    private func remove(_ key: ObjectIdentifier) { lock.lock(); active.remove(key); lock.unlock() }
    func webView(_ webView: WKWebView, stop urlSchemeTask: WKURLSchemeTask) { remove(ObjectIdentifier(urlSchemeTask)) }
    func webView(_ webView: WKWebView, start task: WKURLSchemeTask) {
        let key = ObjectIdentifier(task); lock.lock(); active.insert(key); lock.unlock()
        DispatchQueue.global(qos: .userInitiated).async { [self] in
            do {
                guard let url = task.request.url, url.host == "artifact", let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
                      let project = components.queryItems?.first(where: { $0.name == "project" })?.value else { throw failure("Érvénytelen médiaazonosító.") }
                let aid = url.lastPathComponent
                guard aid.range(of: "^[a-f0-9]{32}$", options: .regularExpression) != nil,
                      project.range(of: "^[A-Za-z0-9_-]{1,64}$", options: .regularExpression) != nil else { throw failure("Érvénytelen médiaazonosító.") }
                let root = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Orbit/core")
                let process = Process(); process.executableURL = URL(fileURLWithPath: "/usr/bin/python3"); process.arguments = [root.appendingPathComponent("bridge.py").path]
                let input = Pipe(), output = Pipe(); process.standardInput = input; process.standardOutput = output; process.standardError = FileHandle.nullDevice
                process.environment = ProcessInfo.processInfo.environment.merging(["PYTHONDONTWRITEBYTECODE": "1"]) { _, new in new }
                try process.run(); try input.fileHandleForWriting.write(contentsOf: JSONSerialization.data(withJSONObject: ["action": "artifact", "project": project, "id": aid])); try input.fileHandleForWriting.close()
                let response = output.fileHandleForReading.readDataToEndOfFile(); process.waitUntilExit()
                guard process.terminationStatus == 0, let object = try JSONSerialization.jsonObject(with: response) as? [String: Any], object["ok"] as? Bool == true, let path = object["path"] as? String else { throw failure("A média nem érhető el.") }
                let file = URL(fileURLWithPath: path), allowed = ["png", "jpg", "jpeg", "webp", "mp4", "mov", "webm", "mp3", "wav", "m4a", "html", "htm"]
                guard allowed.contains(file.pathExtension.lowercased()) else { throw failure("Nem lejátszható médiatípus.") }
                let size = Int64(try file.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0)
                guard size > 0 else { throw failure("Üres médiafájl.") }
                var start: Int64 = 0, end = size - 1, partial = false
                if let range = task.request.value(forHTTPHeaderField: "Range"), range.hasPrefix("bytes=") {
                    let values = range.dropFirst(6).split(separator: "-", omittingEmptySubsequences: false)
                    guard values.count == 2 else { throw failure("Érvénytelen médiatartomány.") }
                    if values[0].isEmpty, let suffix = Int64(values[1]), suffix > 0 { start = max(0, size - suffix) }
                    else { guard let first = Int64(values[0]), first >= 0, first < size else { throw failure("Érvénytelen médiatartomány.") }; start = first; if !values[1].isEmpty { guard let last = Int64(values[1]), last >= first else { throw failure("Érvénytelen médiatartomány.") }; end = min(last, size - 1) } }
                    partial = true
                }
                let length = end - start + 1
                var headers = ["Content-Type": UTType(filenameExtension: file.pathExtension)?.preferredMIMEType ?? "application/octet-stream", "Content-Length": String(length), "Accept-Ranges": "bytes", "Cache-Control": "no-store", "Access-Control-Allow-Origin": "*"]
                if partial { headers["Content-Range"] = "bytes \(start)-\(end)/\(size)" }
                // A generated page has an opaque origin, no network and no access to the app.
                if ["html", "htm"].contains(file.pathExtension.lowercased()) { headers["Content-Security-Policy"] = "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline' data: blob:; style-src 'unsafe-inline' data:; img-src data: blob:; media-src data: blob:; font-src data:" }
                guard let http = HTTPURLResponse(url: url, statusCode: partial ? 206 : 200, httpVersion: "HTTP/1.1", headerFields: headers) else { throw failure("Médiahiba.") }
                DispatchQueue.main.sync { if isActive(key) { task.didReceive(http) } }
                let handle = try FileHandle(forReadingFrom: file); defer { try? handle.close() }; try handle.seek(toOffset: UInt64(start))
                var remaining = length
                while remaining > 0 && isActive(key) {
                    guard let chunk = try handle.read(upToCount: Int(min(remaining, 512 * 1024))), !chunk.isEmpty else { break }
                    remaining -= Int64(chunk.count)
                    DispatchQueue.main.sync { if isActive(key) { task.didReceive(chunk) } }
                }
                DispatchQueue.main.sync { if isActive(key) { task.didFinish(); remove(key) } }
            } catch { DispatchQueue.main.sync { if isActive(key) { task.didFailWithError(error); remove(key) } } }
        }
    }
    private func failure(_ message: String) -> NSError { NSError(domain: "ORBIT.Media", code: 1, userInfo: [NSLocalizedDescriptionKey: message]) }
}
