// ORBIT Hands: the main assistant's own mouse and keyboard on this Mac.
//
// A small accessory app with its own macOS permissions (Accessibility to act, Screen Recording to see).
// The ORBIT worker sends one JSON command per connection on 127.0.0.1:11460 and gets one JSON answer.
// Perception: the accessibility tree of the front window (buttons, fields, links with their exact frames),
// and on-screen text with positions (Vision OCR) where an app exposes no tree. Action: an element's own
// press action where possible (the user's cursor stays put), otherwise a real click that puts the user's
// pointer back afterwards; typing as Unicode key events; shortcuts through the current keyboard layout.
// While it works, a yarn ball floats on screen and a thread runs from it to the exact point it acts on.
import AppKit
import ApplicationServices
import Carbon
import Foundation
import Vision

let PORT: UInt16 = 11460

// MARK: - Cursor overlay (two styles: "orbit" core with a comet trail, and the original "yarn" ball)

var cursorStyle: String = UserDefaults.standard.string(forKey: "cursorStyle") ?? "orbit"
let TEAL = NSColor(calibratedRed: 0.21, green: 0.95, blue: 0.77, alpha: 1)
let PINK = NSColor(calibratedRed: 0.98, green: 0.45, blue: 0.62, alpha: 1)
let VIOLET = NSColor(calibratedRed: 0.55, green: 0.42, blue: 1.0, alpha: 1)

final class YarnView: NSView {
    var ball = NSPoint(x: -200, y: -200)      // Cocoa coordinates of the cursor's centre
    var target: NSPoint? = nil                // where the thread / beam ends
    var thread: CGFloat = 0                   // 0…1, how far it reaches
    var pulse: CGFloat = 0                    // click wave, 1 → 0
    var spin: CGFloat = 0
    var clock: CGFloat = 0
    var trail: [NSPoint] = []                 // recent centres, newest last
    override var isFlipped: Bool { false }

    override func draw(_ dirtyRect: NSRect) {
        guard let ctx = NSGraphicsContext.current?.cgContext else { return }
        if cursorStyle == "yarn" { drawYarn(ctx) } else { drawOrbit(ctx) }
    }

    // The ORBIT core: comet trail, glowing core with a tilted orbit and a moon, a flowing beam to the target,
    // a rotating reticle and a shockwave with sparks on the click.
    func drawOrbit(_ ctx: CGContext) {
        // Comet tail: one continuous, tapering stroke along the recent path, violet at the end, teal at the core.
        let pts = trail + [ball]
        if pts.count > 1 {
            ctx.saveGState()
            ctx.setShadow(offset: .zero, blur: 12, color: TEAL.withAlphaComponent(0.6).cgColor)
            ctx.setLineCap(.round)
            for i in 1..<pts.count {
                let k = CGFloat(i) / CGFloat(pts.count - 1)
                ctx.setLineWidth(1.5 + 16 * k * k)
                let c = k > 0.55 ? TEAL : VIOLET
                ctx.setStrokeColor(c.withAlphaComponent(0.04 + 0.42 * k * k).cgColor)
                ctx.move(to: pts[i - 1])
                ctx.addLine(to: pts[i])
                ctx.strokePath()
            }
            ctx.restoreGState()
        }
        if let t = target, thread > 0 {
            let end = NSPoint(x: ball.x + (t.x - ball.x) * thread, y: ball.y + (t.y - ball.y) * thread)
            let mid = NSPoint(x: (ball.x + end.x) / 2 + (end.y - ball.y) * 0.18, y: (ball.y + end.y) / 2 - (end.x - ball.x) * 0.18)
            let beam = NSBezierPath()
            beam.move(to: ball)
            beam.curve(to: end, controlPoint1: mid, controlPoint2: mid)
            ctx.saveGState()
            ctx.setShadow(offset: .zero, blur: 10, color: TEAL.withAlphaComponent(0.9).cgColor)
            beam.lineWidth = 3.2
            beam.lineCapStyle = .round
            TEAL.withAlphaComponent(0.85).setStroke()
            beam.stroke()
            ctx.restoreGState()
            // Energy flowing along the beam.
            let flow = beam.copy() as! NSBezierPath
            flow.lineWidth = 1.6
            let pattern: [CGFloat] = [6, 10]
            flow.setLineDash(pattern, count: 2, phase: -clock * 60)
            NSColor.white.withAlphaComponent(0.9).setStroke()
            flow.stroke()
            if thread >= 1 {
                // Reticle: four arcs turning around the exact point.
                for q in 0..<4 {
                    let start = (spin * 90).truncatingRemainder(dividingBy: 360) + CGFloat(q) * 90
                    let arc = NSBezierPath()
                    arc.appendArc(withCenter: t, radius: 13, startAngle: start, endAngle: start + 55)
                    arc.lineWidth = 2.2
                    PINK.setStroke()
                    arc.stroke()
                }
                NSColor.white.setFill()
                NSBezierPath(ovalIn: NSRect(x: t.x - 2.5, y: t.y - 2.5, width: 5, height: 5)).fill()
            }
        }
        if let t = target, pulse > 0 {
            for (j, scale) in [CGFloat(1), 0.6].enumerated() {
                let r = 8 + 34 * (1 - pulse) * scale
                let ring = NSBezierPath(ovalIn: NSRect(x: t.x - r, y: t.y - r, width: r * 2, height: r * 2))
                ring.lineWidth = j == 0 ? 3 : 1.6
                (j == 0 ? TEAL : PINK).withAlphaComponent(pulse).setStroke()
                ring.stroke()
            }
            for q in 0..<10 {
                let a = CGFloat(q) / 10 * 2 * .pi + spin
                let d = 10 + 30 * (1 - pulse)
                let p = NSPoint(x: t.x + cos(a) * d, y: t.y + sin(a) * d)
                (q % 2 == 0 ? TEAL : PINK).withAlphaComponent(pulse).setFill()
                NSBezierPath(ovalIn: NSRect(x: p.x - 2, y: p.y - 2, width: 4, height: 4)).fill()
            }
        }
        // Orbit behind the core.
        let tilt = NSAffineTransform()
        tilt.translateX(by: ball.x, yBy: ball.y)
        tilt.rotate(byDegrees: 28)
        let orbit = NSBezierPath(ovalIn: NSRect(x: -27, y: -9, width: 54, height: 18))
        orbit.transform(using: tilt as AffineTransform)
        orbit.lineWidth = 1.5
        TEAL.withAlphaComponent(0.75).setStroke()
        orbit.stroke()
        // Core with a glow.
        let R: CGFloat = 12 + sin(clock * 5) * 0.8
        ctx.saveGState()
        ctx.setShadow(offset: .zero, blur: 22, color: TEAL.withAlphaComponent(0.95).cgColor)
        let core = NSBezierPath(ovalIn: NSRect(x: ball.x - R, y: ball.y - R, width: R * 2, height: R * 2))
        NSGradient(colors: [NSColor.white, TEAL, VIOLET])?.draw(in: core, relativeCenterPosition: NSPoint(x: -0.35, y: 0.35))
        ctx.restoreGState()
        // The moon on the orbit: in front of the core on one half of its path.
        let a = spin * 1.8
        let moon = NSPoint(x: cos(a) * 27, y: sin(a) * 9).applying(CGAffineTransform(rotationAngle: 28 * .pi / 180))
        let mp = NSPoint(x: ball.x + moon.x, y: ball.y + moon.y)
        ctx.saveGState()
        ctx.setShadow(offset: .zero, blur: 8, color: PINK.cgColor)
        PINK.setFill()
        NSBezierPath(ovalIn: NSRect(x: mp.x - 3.6, y: mp.y - 3.6, width: 7.2, height: 7.2)).fill()
        ctx.restoreGState()
    }

    func drawYarn(_ ctx: CGContext) {
        let accent = TEAL
        let wool = PINK
        if let t = target, thread > 0 {
            let end = NSPoint(x: ball.x + (t.x - ball.x) * thread, y: ball.y + (t.y - ball.y) * thread)
            let path = NSBezierPath()
            let dx = t.x - ball.x, dy = t.y - ball.y, len = max(1, (dx * dx + dy * dy).squareRoot())
            path.move(to: NSPoint(x: ball.x + dx / len * 14, y: ball.y + dy / len * 14))
            let mid = NSPoint(x: (ball.x + end.x) / 2, y: (ball.y + end.y) / 2 - 26 * (1 - thread) - 10)
            path.curve(to: end, controlPoint1: mid, controlPoint2: mid)
            path.lineWidth = 3
            path.lineCapStyle = .round
            wool.withAlphaComponent(0.95).setStroke()
            path.stroke()
            if thread >= 1 {
                accent.setFill()
                NSBezierPath(ovalIn: NSRect(x: t.x - 4, y: t.y - 4, width: 8, height: 8)).fill()
            }
        }
        if let t = target, pulse > 0 {
            let r = 6 + 22 * (1 - pulse)
            let ring = NSBezierPath(ovalIn: NSRect(x: t.x - r, y: t.y - r, width: r * 2, height: r * 2))
            ring.lineWidth = 2.5
            accent.withAlphaComponent(pulse).setStroke()
            ring.stroke()
        }
        // The ball: a shadowed body, then strands wound across it in three directions, clipped to the ball.
        let R: CGFloat = 21
        let body = NSRect(x: ball.x - R, y: ball.y - R, width: R * 2, height: R * 2)
        ctx.saveGState()
        ctx.setShadow(offset: CGSize(width: 0, height: -2), blur: 9, color: NSColor.black.withAlphaComponent(0.45).cgColor)
        wool.setFill()
        NSBezierPath(ovalIn: body).fill()
        ctx.restoreGState()
        ctx.saveGState()
        NSBezierPath(ovalIn: body).addClip()
        let dark = NSColor(calibratedRed: 0.78, green: 0.22, blue: 0.43, alpha: 0.95)
        let light = NSColor(calibratedRed: 1, green: 0.72, blue: 0.82, alpha: 0.9)
        for (n, base) in [CGFloat(0.35), 1.45, 2.55].enumerated() {
            for k in -3...3 {
                let t = NSAffineTransform()
                t.translateX(by: ball.x, yBy: ball.y)
                t.rotate(byRadians: base + spin * (n == 1 ? 0.6 : 0.3))
                let strand = NSBezierPath(ovalIn: NSRect(x: -R * 1.05, y: CGFloat(k) * 4.2 - R * 0.42, width: R * 2.1, height: R * 0.84))
                strand.transform(using: t as AffineTransform)
                strand.lineWidth = 1.15
                ((k + n) % 2 == 0 ? dark : light).setStroke()
                strand.stroke()
            }
        }
        // A soft highlight gives the ball its roundness.
        let glow = NSGradient(colors: [NSColor.white.withAlphaComponent(0.45), NSColor.white.withAlphaComponent(0)])
        glow?.draw(in: NSBezierPath(ovalIn: NSRect(x: ball.x - R * 0.9, y: ball.y, width: R * 1.1, height: R * 0.9)), relativeCenterPosition: NSPoint(x: -0.2, y: 0.3))
        ctx.restoreGState()
        let rim = NSBezierPath(ovalIn: body)
        rim.lineWidth = 1.2
        NSColor(calibratedRed: 0.55, green: 0.12, blue: 0.3, alpha: 0.75).setStroke()
        rim.stroke()
    }
}

final class Overlay {
    // One transparent, click-through window per display: a single window spanning several displays is not shown
    // when "Displays have separate Spaces" is on (the macOS default).
    var windows: [NSWindow] = []
    var views: [YarnView] = []
    var hideTimer: Timer?
    var current = NSPoint(x: -10000, y: -10000)   // ball centre, Cocoa global coordinates

    init() { rebuild() }

    func rebuild() {
        windows.forEach { $0.orderOut(nil) }
        windows = []
        views = []
        for screen in NSScreen.screens {
            let w = NSWindow(contentRect: screen.frame, styleMask: .borderless, backing: .buffered, defer: false, screen: screen)
            w.setFrame(screen.frame, display: false)
            w.isOpaque = false
            w.backgroundColor = .clear
            w.hasShadow = false
            w.ignoresMouseEvents = true
            w.level = NSWindow.Level(rawValue: Int(CGShieldingWindowLevel()))
            w.collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary, .ignoresCycle]
            let v = YarnView(frame: NSRect(origin: .zero, size: screen.frame.size))
            w.contentView = v
            windows.append(w)
            views.append(v)
        }
    }

    // Quartz (top-left origin of the primary display) → Cocoa global coordinates.
    func cocoa(_ q: CGPoint) -> NSPoint {
        let primary = NSScreen.screens.first?.frame.height ?? 0
        return NSPoint(x: q.x, y: primary - q.y)
    }

    func paint(ball: NSPoint, target: NSPoint?, thread: CGFloat, pulse: CGFloat, spin: CGFloat) {
        for (w, v) in zip(windows, views) {
            let o = w.frame.origin
            v.ball = NSPoint(x: ball.x - o.x, y: ball.y - o.y)
            v.target = target.map { NSPoint(x: $0.x - o.x, y: $0.y - o.y) }
            v.thread = thread
            v.pulse = pulse
            v.spin = spin
            v.clock = clock
            v.trail = trail.map { NSPoint(x: $0.x - o.x, y: $0.y - o.y) }
            v.needsDisplay = true
            v.displayIfNeeded()
        }
    }

    func show() {
        hideTimer?.invalidate()
        // A hidden app's windows never appear; unhide without taking focus from the user's app.
        if NSApp.isHidden { NSApp.unhideWithoutActivation() }
        if windows.count != NSScreen.screens.count { rebuild() }
        windows.forEach { $0.orderFrontRegardless() }
        if ticker == nil {
            // A 60 fps clock on the main run loop: every frame is really composited, so the ball moves live.
            ticker = Timer(timeInterval: 1.0 / 60, repeats: true) { [weak self] _ in self?.tick() }
            RunLoop.main.add(ticker!, forMode: .common)
        }
    }

    func scheduleHide() {
        hideTimer?.invalidate()
        hideTimer = Timer.scheduledTimer(withTimeInterval: 12, repeats: false) { [weak self] _ in
            guard let self = self else { return }
            self.windows.forEach { $0.orderOut(nil) }
            self.ticker?.invalidate()
            self.ticker = nil
        }
    }

    // Live animation state.
    var ticker: Timer?
    var from = NSPoint.zero, to = NSPoint.zero
    var targetPoint: NSPoint? = nil
    var started = Date.distantPast
    var duration: TimeInterval = 0.55
    var clicking = false
    var done: (() -> Void)? = nil
    var spin: CGFloat = 0
    var clock: CGFloat = 0
    var trail: [NSPoint] = []

    func tick() {
        clock += 1.0 / 60
        spin += 0.06
        let k = CGFloat(min(1, Date().timeIntervalSince(started) / duration))
        let e = k < 0.5 ? 2 * k * k : 1 - pow(-2 * k + 2, 2) / 2
        var ball = NSPoint(x: from.x + (to.x - from.x) * e, y: from.y + (to.y - from.y) * e)
        if k >= 1 { ball.y += sin(clock * 2.4) * 3 }          // a gentle float while it waits
        current = k >= 1 ? to : ball
        let thread = targetPoint == nil ? 0 : max(0, (k - 0.3) / 0.7)
        var pulse: CGFloat = 0
        if clicking {
            let after = Date().timeIntervalSince(started) - duration
            if after >= 0 { pulse = CGFloat(max(0, 1 - after / 0.25)) }
        }
        // Comet trail: the last positions while moving; it fades away while the cursor rests.
        if k < 1 { trail.append(ball) } else if !trail.isEmpty { trail.removeFirst() }
        if trail.count > 22 { trail.removeFirst(trail.count - 22) }
        paint(ball: ball, target: targetPoint, thread: thread, pulse: pulse, spin: spin)
        if k >= 1, let finish = done, !clicking || Date().timeIntervalSince(started) - duration >= 0.12 {
            done = nil
            finish()
        }
    }

    /// Starts the flight to a Quartz point (main thread). completion runs when the thread has reached it.
    func fly(to q: CGPoint, click: Bool, completion: @escaping () -> Void) {
        let wasHidden = !(windows.first?.isVisible ?? false)
        show()
        let t = cocoa(q)
        targetPoint = t
        let goal = NSPoint(x: t.x + offset.x, y: t.y + offset.y)
        // A hidden ball starts at the owner's own pointer, so the eye follows it from where it already looks.
        let hidden = current.x < -9000 || wasHidden
        let mouse = NSEvent.mouseLocation
        from = hidden ? NSPoint(x: mouse.x + offset.x, y: mouse.y + offset.y) : current
        to = goal
        let distance = hypot(goal.x - from.x, goal.y - from.y)
        duration = min(1.1, max(0.6, Double(distance) / 1400))
        started = Date()
        clicking = click
        done = completion
        scheduleHide()
    }

    /// From a background thread: fly there and wait until the thread touches the point (max 2 s).
    func flyAndWait(to q: CGPoint, click: Bool) {
        let sem = DispatchSemaphore(value: 0)
        DispatchQueue.main.async { self.fly(to: q, click: click) { sem.signal() } }
        _ = sem.wait(timeout: .now() + 2.5)
    }

    var offset: NSPoint { cursorStyle == "yarn" ? NSPoint(x: 46, y: 40) : NSPoint(x: 58, y: 52) }

    func reach(to q: CGPoint, click: Bool) {
        // Kept for direct calls on the main thread: no blocking animation, just the final pose.
        show()
        let t = cocoa(q)
        targetPoint = t
        to = NSPoint(x: t.x + 46, y: t.y + 40)
        from = to
        started = Date.distantPast
        scheduleHide()
    }

    func idle(at q: CGPoint?) {
        show()
        if let q = q { let t = cocoa(q); current = NSPoint(x: t.x + 46, y: t.y + 40) }
        if current.x < -9000, let f = NSScreen.main?.frame { current = NSPoint(x: f.midX, y: f.midY) }
        from = current
        to = current
        targetPoint = nil
        started = Date.distantPast
        scheduleHide()
    }
}

/// Where the ball should point for a command, resolved on the main thread before the action.
func pointFor(_ req: [String: Any]) -> CGPoint? {
    let cmd = req["cmd"] as? String ?? ""
    if ["click", "focus"].contains(cmd), let i = req["index"] as? Int, i >= 0, i < lastElements.count, let f = frame(lastElements[i]) {
        return CGPoint(x: f.midX, y: f.midY)
    }
    if ["click", "scroll", "point"].contains(cmd), let x = req["x"] as? Double, let y = req["y"] as? Double { return CGPoint(x: x, y: y) }
    // Without coordinates the ball still goes where the work happens: the window of the named (or front) app.
    if ["scroll", "point", "activate"].contains(cmd) { return windowCenter(req["app"] as? String) }
    if cmd == "type" || cmd == "key" {
        var focused: AnyObject?
        if AXUIElementCopyAttributeValue(AXUIElementCreateSystemWide(), kAXFocusedUIElementAttribute as CFString, &focused) == .success,
           let f = frame(focused as! AXUIElement), f.width > 2 {
            return CGPoint(x: min(f.maxX - 8, f.minX + 40), y: f.midY)
        }
        return windowCenter(nil)
    }
    return nil
}

// MARK: - Menu bar: clearly shows when ORBIT controls the Mac, with a stop

let ORBIT_EVENT_TAG: Int64 = 0x0B17   // marks ORBIT's own synthetic events, so its Escape never stops itself

final class StatusBar: NSObject {
    let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    var busyUntil = Date.distantPast
    var label = ""
    var stopRequested = false
    var timer: Timer?
    var phase: CGFloat = 0
    let activityItem = NSMenuItem(title: "Az ORBIT most nem vezérli a gépet", action: nil, keyEquivalent: "")

    override init() {
        super.init()
        let menu = NSMenu()
        menu.addItem(activityItem)
        menu.addItem(NSMenuItem.separator())
        let stop = NSMenuItem(title: "Vezérlés leállítása (Esc)", action: #selector(stopNow), keyEquivalent: "")
        stop.target = self
        menu.addItem(stop)
        menu.addItem(NSMenuItem.separator())
        let header = NSMenuItem(title: "Kurzor", action: nil, keyEquivalent: "")
        header.isEnabled = false
        menu.addItem(header)
        for (key, title) in [("orbit", "ORBIT mag"), ("yarn", "Fonalgombolyag")] {
            let m = NSMenuItem(title: title, action: #selector(pickStyle(_:)), keyEquivalent: "")
            m.target = self
            m.representedObject = key
            menu.addItem(m)
        }
        item.menu = menu
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 1.0 / 12, repeats: true) { [weak self] _ in self?.refresh() }
    }

    var busy: Bool { Date() < busyUntil }

    func touch(_ text: String?) {
        if let t = text, !t.isEmpty { label = t }
        busyUntil = Date().addingTimeInterval(6)
    }

    func begin(_ text: String) { stopRequested = false; label = text; busyUntil = Date().addingTimeInterval(600) }
    func end() { busyUntil = Date(); label = "" }

    @objc func stopNow() {
        stopRequested = true
        end()
        overlay.windows.forEach { $0.orderOut(nil) }
    }

    @objc func pickStyle(_ sender: NSMenuItem) {
        setStyle(sender.representedObject as? String ?? "orbit")
    }

    func refresh() {
        guard let button = item.button else { return }
        item.menu?.items.forEach { if let k = $0.representedObject as? String { $0.state = k == cursorStyle ? .on : .off } }
        if busy {
            phase += 0.35
            let glow = 0.55 + 0.45 * abs(sin(phase))
            let text = NSMutableAttributedString(string: "◉ ", attributes: [.foregroundColor: TEAL.withAlphaComponent(glow), .font: NSFont.systemFont(ofSize: 13, weight: .bold)])
            text.append(NSAttributedString(string: "ORBIT vezérel", attributes: [.foregroundColor: NSColor.labelColor, .font: NSFont.systemFont(ofSize: 12, weight: .semibold)]))
            button.attributedTitle = text
            button.toolTip = label.isEmpty ? "Az ORBIT vezérli a gépet" : label
            activityItem.title = "Most: " + (label.isEmpty ? "dolgozik" : String(label.prefix(70)))
        } else {
            button.attributedTitle = NSAttributedString(string: "◎", attributes: [.foregroundColor: NSColor.secondaryLabelColor, .font: NSFont.systemFont(ofSize: 14, weight: .regular)])
            button.toolTip = "ORBIT Hands · most nem vezérli a gépet"
            activityItem.title = "Az ORBIT most nem vezérli a gépet"
        }
    }
}

func setStyle(_ name: String) {
    cursorStyle = name == "yarn" ? "yarn" : "orbit"
    UserDefaults.standard.set(cursorStyle, forKey: "cursorStyle")
    overlay.views.forEach { $0.needsDisplay = true }
}

var statusBar: StatusBar! = nil

// MARK: - Keyboard layout

var keyForChar: [Character: CGKeyCode] = [:]

func buildKeyMap() {
    guard let source = TISCopyCurrentKeyboardLayoutInputSource()?.takeRetainedValue(),
          let raw = TISGetInputSourceProperty(source, kTISPropertyUnicodeKeyLayoutData) else { return }
    let data = Unmanaged<CFData>.fromOpaque(raw).takeUnretainedValue() as Data
    data.withUnsafeBytes { (ptr: UnsafeRawBufferPointer) in
        guard let layout = ptr.baseAddress?.assumingMemoryBound(to: UCKeyboardLayout.self) else { return }
        for code in 0..<128 {
            var dead: UInt32 = 0
            var length = 0
            var chars = [UniChar](repeating: 0, count: 4)
            let status = UCKeyTranslate(layout, UInt16(code), UInt16(kUCKeyActionDown), 0, UInt32(LMGetKbdType()),
                                        OptionBits(kUCKeyTranslateNoDeadKeysBit), &dead, 4, &length, &chars)
            if status == noErr, length == 1, let scalar = UnicodeScalar(chars[0]) {
                let c = Character(scalar).lowercased().first!
                if keyForChar[c] == nil { keyForChar[c] = CGKeyCode(code) }
            }
        }
    }
}

let NAMED: [String: CGKeyCode] = ["return": 36, "enter": 36, "tab": 48, "space": 49, "delete": 51, "backspace": 51,
    "escape": 53, "esc": 53, "left": 123, "right": 124, "down": 125, "up": 126, "home": 115, "end": 119,
    "pageup": 116, "pagedown": 121, "forwarddelete": 117, "f5": 96]

func press(_ combo: String) throws {
    let parts = combo.lowercased().replacingOccurrences(of: " ", with: "").split(separator: "+").map(String.init)
    guard let key = parts.last, !key.isEmpty else { throw HandsError.bad("Üres billentyűparancs.") }
    var flags = CGEventFlags()
    for m in parts.dropLast() {
        switch m {
        case "cmd", "command": flags.insert(.maskCommand)
        case "ctrl", "control": flags.insert(.maskControl)
        case "alt", "option": flags.insert(.maskAlternate)
        case "shift": flags.insert(.maskShift)
        default: throw HandsError.bad("Ismeretlen módosító: \(m)")
        }
    }
    var code: CGKeyCode
    if let n = NAMED[key] { code = n }
    else if key.count == 1, let c = keyForChar[key.first!] { code = c }
    else { throw HandsError.bad("Ismeretlen billentyű: \(key)") }
    let src = CGEventSource(stateID: .hidSystemState)
    for down in [true, false] {
        let e = CGEvent(keyboardEventSource: src, virtualKey: code, keyDown: down)
        e?.setIntegerValueField(.eventSourceUserData, value: ORBIT_EVENT_TAG)
        e?.flags = flags
        e?.post(tap: .cghidEventTap)
        usleep(12000)
    }
}

func typeText(_ text: String) {
    let src = CGEventSource(stateID: .hidSystemState)
    let units = Array(text.utf16)
    var i = 0
    while i < units.count {
        var chunk = Array(units[i..<min(i + 16, units.count)])
        // Keep surrogate pairs together.
        if let last = chunk.last, UTF16.isLeadSurrogate(last), i + chunk.count < units.count { chunk.append(units[i + chunk.count]) }
        for down in [true, false] {
            let e = CGEvent(keyboardEventSource: src, virtualKey: 0, keyDown: down)
            e?.setIntegerValueField(.eventSourceUserData, value: ORBIT_EVENT_TAG)
            e?.keyboardSetUnicodeString(stringLength: chunk.count, unicodeString: &chunk)
            e?.post(tap: .cghidEventTap)
        }
        usleep(8000)
        i += chunk.count
    }
}

// MARK: - Accessibility tree

enum HandsError: Error { case bad(String) }

let INTERACTIVE: Set<String> = ["AXButton", "AXTextField", "AXTextArea", "AXSearchField", "AXLink", "AXMenuItem",
    "AXMenuButton", "AXCheckBox", "AXRadioButton", "AXPopUpButton", "AXComboBox", "AXTab", "AXTabButton",
    "AXDisclosureTriangle", "AXSlider", "AXIncrementor", "AXCell", "AXRow", "AXImage", "AXStaticText", "AXHeading"]

func attr(_ el: AXUIElement, _ name: String) -> AnyObject? {
    var v: AnyObject?
    return AXUIElementCopyAttributeValue(el, name as CFString, &v) == .success ? v : nil
}

func frame(_ el: AXUIElement) -> CGRect? {
    guard let p = attr(el, kAXPositionAttribute), let s = attr(el, kAXSizeAttribute) else { return nil }
    var point = CGPoint.zero, size = CGSize.zero
    AXValueGetValue(p as! AXValue, .cgPoint, &point)
    AXValueGetValue(s as! AXValue, .cgSize, &size)
    return CGRect(origin: point, size: size)
}

func label(_ el: AXUIElement) -> String {
    for key in [kAXTitleAttribute, kAXDescriptionAttribute, "AXPlaceholderValue", kAXValueAttribute, kAXHelpAttribute] {
        if let s = attr(el, key) as? String {
            let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
            if !t.isEmpty { return String(t.prefix(90)) }
        }
    }
    return ""
}

var lastElements: [AXUIElement] = []

/// The middle of an app's focused (or first) window, Quartz coordinates; nil when it has no window yet.
func windowCenter(_ name: String?) -> CGPoint? {
    guard let app = frontApp(name) else { return nil }
    let root = AXUIElementCreateApplication(app.processIdentifier)
    var win = attr(root, kAXFocusedWindowAttribute)
    if win == nil, let list = attr(root, kAXWindowsAttribute) as? [AnyObject], let first = list.first { win = first }
    guard let w = win, let f = frame(w as! AXUIElement), f.width > 40 else { return nil }
    return CGPoint(x: f.midX, y: f.minY + min(f.height / 2, 260))
}

func frontApp(_ name: String?) -> NSRunningApplication? {
    if let name = name, !name.isEmpty {
        // Match the localized name ("Jegyzetek") and the bundle's own name ("Notes.app") alike.
        let n = name.lowercased()
        let apps = NSWorkspace.shared.runningApplications.filter { $0.activationPolicy == .regular }
        func names(_ a: NSRunningApplication) -> [String] {
            [(a.localizedName ?? "").lowercased(), (a.bundleURL?.deletingPathExtension().lastPathComponent ?? "").lowercased()]
        }
        return apps.first { names($0).contains(n) } ?? apps.first { names($0).contains { $0.contains(n) } }
    }
    return NSWorkspace.shared.frontmostApplication
}

func displays() -> [[String: Any]] {
    let primary = NSScreen.screens.first?.frame.height ?? 0
    return NSScreen.screens.enumerated().map { (i, s) in
        let f = s.frame
        // Quartz coordinates (top-left origin), the same space as element positions and clicks.
        return ["index": i, "main": i == 0, "x": Int(f.minX), "y": Int(primary - f.maxY), "w": Int(f.width), "h": Int(f.height), "name": s.localizedName]
    }
}

func elements(app name: String?, limit: Int) -> [String: Any] {
    guard let app = frontApp(name) else { return ["app": "", "elements": []] }
    let root = AXUIElementCreateApplication(app.processIdentifier)
    // Chromium and Electron build their web accessibility tree only when asked.
    AXUIElementSetAttributeValue(root, "AXManualAccessibility" as CFString, kCFBooleanTrue)
    AXUIElementSetAttributeValue(root, "AXEnhancedUserInterface" as CFString, kCFBooleanTrue)
    var start: [AXUIElement] = []
    if let w = attr(root, kAXFocusedWindowAttribute) { start.append(w as! AXUIElement) }
    else if let ws = attr(root, kAXWindowsAttribute) as? [AXUIElement], let w = ws.first { start.append(w) }
    if let bar = attr(root, kAXMenuBarAttribute) { _ = bar }
    let screen = NSScreen.screens.reduce(CGRect.zero) { $0.union($1.frame) }
    var queue = start.map { ($0, 0) }
    var found: [[String: Any]] = []
    lastElements = []
    var visited = 0
    var title = ""
    if let w = start.first { title = (attr(w, kAXTitleAttribute) as? String) ?? "" }
    while !queue.isEmpty && found.count < limit && visited < 6000 {
        let (el, depth) = queue.removeFirst()
        visited += 1
        let role = (attr(el, kAXRoleAttribute) as? String) ?? ""
        if INTERACTIVE.contains(role), let f = frame(el), f.width >= 3, f.height >= 3, screen.intersects(f) {
            let text = label(el)
            if !(role == "AXStaticText" || role == "AXImage" || role == "AXHeading" || role == "AXRow" || role == "AXCell") || !text.isEmpty {
                var actions: CFArray?
                AXUIElementCopyActionNames(el, &actions)
                let pressable = ((actions as? [String]) ?? []).contains(kAXPressAction)
                lastElements.append(el)
                found.append(["i": lastElements.count - 1, "role": role.replacingOccurrences(of: "AX", with: ""), "label": text,
                              "x": Int(f.midX), "y": Int(f.midY), "w": Int(f.width), "h": Int(f.height), "press": pressable,
                              "focused": (attr(el, kAXFocusedAttribute) as? Bool) ?? false])
            }
        }
        if depth < 40, let kids = attr(el, kAXChildrenAttribute) as? [AXUIElement] {
            queue.append(contentsOf: kids.map { ($0, depth + 1) })
        }
    }
    var win: [String: Int] = [:]
    if let w = start.first, let f = frame(w) { win = ["x": Int(f.minX), "y": Int(f.minY), "w": Int(f.width), "h": Int(f.height)] }
    var windowCount = 0
    if let ws = attr(root, kAXWindowsAttribute) as? [AXUIElement] { windowCount = ws.count }
    return ["app": app.localizedName ?? "", "window": title, "elements": found, "visited": visited, "has_window": !start.isEmpty,
            "window_frame": win, "windows": windowCount, "displays": displays()]
}

// MARK: - Seeing: screenshot and on-screen text

func screenshot(_ path: String) throws {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
    p.arguments = ["-x", "-m", path]
    try p.run()
    p.waitUntilExit()
    if p.terminationStatus != 0 || !FileManager.default.fileExists(atPath: path) {
        throw HandsError.bad("Képernyőkép nem készült: a Képernyőfelvétel engedély hiányzik az ORBIT Hands-nek.")
    }
}

func ocr(limit: Int) throws -> [[String: Any]] {
    let path = NSTemporaryDirectory() + "orbit-hands-ocr.png"
    try screenshot(path)
    defer { try? FileManager.default.removeItem(atPath: path) }
    guard let image = NSImage(contentsOfFile: path)?.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return [] }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["hu-HU", "en-US"]
    request.usesLanguageCorrection = true
    try VNImageRequestHandler(cgImage: image, options: [:]).perform([request])
    let main = NSScreen.screens.first?.frame ?? .zero
    var out: [[String: Any]] = []
    for obs in (request.results ?? []).prefix(limit) {
        guard let text = obs.topCandidates(1).first?.string else { continue }
        let b = obs.boundingBox  // normalised, bottom-left origin, of the main display
        let x = (b.midX) * main.width
        let y = (1 - b.midY) * main.height
        out.append(["text": String(text.prefix(90)), "x": Int(x), "y": Int(y)])
    }
    return out
}

// MARK: - Acting

let overlay = Overlay()

func click(at q: CGPoint, double: Bool = false, right: Bool = false) {
    let src = CGEventSource(stateID: .hidSystemState)
    let saved = CGEvent(source: nil)?.location ?? q
    let (downType, upType, button): (CGEventType, CGEventType, CGMouseButton) = right ? (.rightMouseDown, .rightMouseUp, .right) : (.leftMouseDown, .leftMouseUp, .left)
    CGEvent(mouseEventSource: src, mouseType: .mouseMoved, mouseCursorPosition: q, mouseButton: button)?.post(tap: .cghidEventTap)
    usleep(30000)
    for n in 1...(double ? 2 : 1) {
        let d = CGEvent(mouseEventSource: src, mouseType: downType, mouseCursorPosition: q, mouseButton: button)
        d?.setIntegerValueField(.mouseEventClickState, value: Int64(n))
        d?.post(tap: .cghidEventTap)
        usleep(25000)
        let u = CGEvent(mouseEventSource: src, mouseType: upType, mouseCursorPosition: q, mouseButton: button)
        u?.setIntegerValueField(.mouseEventClickState, value: Int64(n))
        u?.post(tap: .cghidEventTap)
        usleep(40000)
    }
    // The user's own pointer goes back where it was.
    CGWarpMouseCursorPosition(saved)
}

func openSettings(_ which: String) {
    let pane = which == "screen" ? "Privacy_ScreenCapture" : "Privacy_Accessibility"
    if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?\(pane)") { NSWorkspace.shared.open(url) }
}

func status() -> [String: Any] {
    // A real AX call as well as the flag: -25211 (API disabled) means macOS does not trust this exact build.
    var focused: AnyObject?
    let probe = AXUIElementCopyAttributeValue(AXUIElementCreateSystemWide(), kAXFocusedApplicationAttribute as CFString, &focused)
    return ["ok": true, "accessibility": AXIsProcessTrusted(), "screen": CGPreflightScreenCaptureAccess(),
            "ax_probe": Int(probe.rawValue), "app": Bundle.main.bundlePath, "pid": ProcessInfo.processInfo.processIdentifier,
            "bundle": Bundle.main.bundleIdentifier ?? "", "style": cursorStyle]
}

func handle(_ req: [String: Any]) -> [String: Any] {
    var reply = handleCommand(req)
    let cmd = req["cmd"] as? String ?? ""
    if statusBar.stopRequested && !["status", "begin", "end", "style", "preview", "diag", "displays"].contains(cmd) {
        reply = ["ok": false, "error": "stopped"]
    }
    return reply
}

func handleCommand(_ req: [String: Any]) -> [String: Any] {
    let cmd = req["cmd"] as? String ?? ""
    if ["click", "type", "key", "scroll", "focus", "activate", "point", "elements", "ocr", "show"].contains(cmd) {
        if statusBar.stopRequested { return ["ok": false, "error": "stopped"] }
        statusBar.touch(req["label"] as? String)
    }
    if ["elements", "ocr", "click", "type", "key", "scroll", "focus", "activate"].contains(cmd) { overlay.show(); overlay.scheduleHide() }
    do {
        switch cmd {
        case "status":
            return status()
        case "request":
            // The system dialog and the exact Settings pane where ORBIT Hands has to be switched on.
            let which = req["which"] as? String ?? "accessibility"
            if which == "screen" { if !CGPreflightScreenCaptureAccess() { _ = CGRequestScreenCaptureAccess() } }
            else { _ = AXIsProcessTrustedWithOptions([kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary) }
            openSettings(which)
            return status()
        case "settings":
            openSettings(req["which"] as? String ?? "accessibility")
            return ["ok": true]
        case "elements":
            guard AXIsProcessTrusted() else { throw HandsError.bad("permission:accessibility") }
            var r = elements(app: req["app"] as? String, limit: req["limit"] as? Int ?? 150)
            r["ok"] = true
            return r
        case "ocr":
            guard CGPreflightScreenCaptureAccess() else { throw HandsError.bad("permission:screen") }
            return ["ok": true, "texts": try ocr(limit: req["limit"] as? Int ?? 160)]
        case "screenshot":
            guard CGPreflightScreenCaptureAccess() else { throw HandsError.bad("permission:screen") }
            let path = req["path"] as? String ?? (NSTemporaryDirectory() + "orbit-shot.png")
            try screenshot(path)
            return ["ok": true, "path": path]
        case "click":
            guard AXIsProcessTrusted() else { throw HandsError.bad("permission:accessibility") }
            if let i = req["index"] as? Int {
                guard i >= 0 && i < lastElements.count else { throw HandsError.bad("Nincs ilyen elem: \(i). Előbb olvasd be újra a képernyőt.") }
                let el = lastElements[i]
                guard let f = frame(el) else { throw HandsError.bad("Az elem már nem látható.") }
                let q = CGPoint(x: f.midX, y: f.midY)
                var actions: CFArray?
                AXUIElementCopyActionNames(el, &actions)
                let canPress = ((actions as? [String]) ?? []).contains(kAXPressAction)
                if canPress && !(req["double"] as? Bool ?? false) && !(req["right"] as? Bool ?? false) {
                    if AXUIElementPerformAction(el, kAXPressAction as CFString) == .success { return ["ok": true, "x": Int(q.x), "y": Int(q.y), "via": "press"] }
                }
                click(at: q, double: req["double"] as? Bool ?? false, right: req["right"] as? Bool ?? false)
                return ["ok": true, "x": Int(q.x), "y": Int(q.y), "via": "mouse"]
            }
            guard let x = req["x"] as? Double, let y = req["y"] as? Double else { throw HandsError.bad("Kattintáshoz elem sorszám vagy x,y kell.") }
            click(at: CGPoint(x: x, y: y), double: req["double"] as? Bool ?? false, right: req["right"] as? Bool ?? false)
            return ["ok": true, "x": Int(x), "y": Int(y), "via": "mouse"]
        case "focus":
            // Focus a text field by index (its value is not changed).
            guard let i = req["index"] as? Int, i >= 0 && i < lastElements.count else { throw HandsError.bad("Nincs ilyen elem.") }
            AXUIElementSetAttributeValue(lastElements[i], kAXFocusedAttribute as CFString, kCFBooleanTrue)
            return ["ok": true]
        case "type":
            guard AXIsProcessTrusted() else { throw HandsError.bad("permission:accessibility") }
            let text = req["text"] as? String ?? ""
            overlay.show()
            overlay.scheduleHide()
            // Insert at the caret of the focused field through accessibility (exact, no keyboard layout involved);
            // the value is read back, and synthetic key events are the fallback.
            var focused: AnyObject?
            if AXUIElementCopyAttributeValue(AXUIElementCreateSystemWide(), kAXFocusedUIElementAttribute as CFString, &focused) == .success {
                let el = focused as! AXUIElement
                let before = (attr(el, kAXValueAttribute) as? String) ?? ""
                if AXUIElementSetAttributeValue(el, kAXSelectedTextAttribute as CFString, text as CFString) == .success {
                    usleep(150000)
                    let after = (attr(el, kAXValueAttribute) as? String) ?? ""
                    if after.count >= before.count + max(1, text.count / 2) || after.contains(String(text.prefix(12))) {
                        return ["ok": true, "typed": text.count, "via": "accessibility"]
                    }
                }
            }
            typeText(text)
            return ["ok": true, "typed": text.count, "via": "keys"]
        case "key":
            guard AXIsProcessTrusted() else { throw HandsError.bad("permission:accessibility") }
            try press(req["combo"] as? String ?? "")
            return ["ok": true]
        case "scroll":
            guard AXIsProcessTrusted() else { throw HandsError.bad("permission:accessibility") }
            let dy = Int32(req["dy"] as? Int ?? -5), dx = Int32(req["dx"] as? Int ?? 0)
            // A wheel event goes to the window under the pointer: scroll over the target, then put the pointer back.
            var at: CGPoint? = nil
            if let x = req["x"] as? Double, let y = req["y"] as? Double { at = CGPoint(x: x, y: y) }
            else if let app = frontApp(req["app"] as? String) {
                let root = AXUIElementCreateApplication(app.processIdentifier)
                if let w = attr(root, kAXFocusedWindowAttribute), let f = frame(w as! AXUIElement) { at = CGPoint(x: f.midX, y: f.midY) }
            }
            let saved = CGEvent(source: nil)?.location
            if let p = at { CGWarpMouseCursorPosition(p); usleep(30000) }
            let steps = max(1, Int(req["times"] as? Int ?? 1))
            for _ in 0..<steps {
                CGEvent(scrollWheelEvent2Source: nil, units: .line, wheelCount: 2, wheel1: dy, wheel2: dx, wheel3: 0)?.post(tap: .cghidEventTap)
                usleep(60000)
            }
            if at != nil, let back = saved { usleep(30000); CGWarpMouseCursorPosition(back) }
            return ["ok": true, "x": Int(at?.x ?? -1), "y": Int(at?.y ?? -1)]
        case "show":
            let q = (req["x"] as? Double).flatMap { x in (req["y"] as? Double).map { CGPoint(x: x, y: $0) } }
            overlay.idle(at: q)
            return ["ok": true]
        case "begin":
            statusBar.begin(req["label"] as? String ?? "Gépkezelés")
            overlay.show()
            overlay.scheduleHide()
            return ["ok": true]
        case "end":
            statusBar.end()
            return ["ok": true]
        case "style":
            if let name = req["name"] as? String { setStyle(name) }
            return ["ok": true, "style": cursorStyle]
        case "displays":
            return ["ok": true, "displays": displays()]
        case "topapp":
            // The app of the front-most normal window that is not ORBIT itself (the user just typed in ORBIT's chat).
            let list = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] ?? []
            let skip: Set<String> = ["Orbit", "ORBIT", "ORBIT Hands", "OrbitHands", "Window Server", "Dock", "Control Center", "Vezérlőközpont", "Notification Center", "SystemUIServer"]
            for w in list where (w[kCGWindowLayer as String] as? Int) == 0 {
                let owner = w[kCGWindowOwnerName as String] as? String ?? ""
                if !skip.contains(owner) && !owner.isEmpty { return ["ok": true, "app": owner] }
            }
            return ["ok": true, "app": ""]
        case "point":
            // The flight itself ran before the command; ok tells the caller whether there was a window to point at.
            return ["ok": pointFor(req) != nil]
        case "diag":
            let mine = (CGWindowListCopyWindowInfo([.optionAll], kCGNullWindowID) as? [[String: Any]] ?? []).filter { ($0[kCGWindowOwnerPID as String] as? Int32) == ProcessInfo.processInfo.processIdentifier }
            return ["ok": true, "screens": NSScreen.screens.map { "\($0.frame)" },
                    "windows": overlay.windows.map { ["frame": "\($0.frame)", "visible": $0.isVisible, "level": $0.level.rawValue, "screen": "\($0.screen?.frame ?? .zero)"] },
                    "server": mine.map { ["bounds": "\($0[kCGWindowBounds as String] ?? "")", "layer": $0[kCGWindowLayer as String] ?? 0, "onscreen": $0[kCGWindowIsOnscreen as String] ?? false, "alpha": $0[kCGWindowAlpha as String] ?? 0] }]
        case "preview":
            // The yarn cursor drawn into a PNG (Settings shows it; needs no permission).
            // The chosen style (or "style" in the request) drawn into a PNG for Settings.
            let keep = cursorStyle
            if let st = req["style"] as? String { cursorStyle = st }
            defer { cursorStyle = keep }
            let v = YarnView(frame: NSRect(x: 0, y: 0, width: 260, height: 170))
            v.ball = NSPoint(x: 190, y: 110)
            v.target = NSPoint(x: 60, y: 45)
            v.thread = 1
            v.pulse = 0.55
            v.spin = 0.7
            v.clock = 0.4
            v.trail = (0..<16).map { i in NSPoint(x: 250 - CGFloat(i) * 3.6, y: 160 - CGFloat(i) * 3.2) }
            guard let rep = v.bitmapImageRepForCachingDisplay(in: v.bounds) else { throw HandsError.bad("Előnézet nem készült.") }
            v.cacheDisplay(in: v.bounds, to: rep)
            let path = req["path"] as? String ?? (NSTemporaryDirectory() + "orbit-yarn.png")
            try rep.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: path))
            return ["ok": true, "path": path]
        case "activate":
            guard let app = frontApp(req["app"] as? String) else { throw HandsError.bad("Nem fut ilyen alkalmazás.") }
            app.activate(options: [])
            return ["ok": true, "app": app.localizedName ?? ""]
        default:
            throw HandsError.bad("Ismeretlen parancs: \(cmd)")
        }
    } catch HandsError.bad(let m) {
        return ["ok": false, "error": m]
    } catch {
        return ["ok": false, "error": error.localizedDescription]
    }
}

// MARK: - Loopback server: one JSON line in, one JSON line out

func serve() {
    let fd = socket(AF_INET, SOCK_STREAM, 0)
    var yes: Int32 = 1
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, socklen_t(MemoryLayout<Int32>.size))
    var addr = sockaddr_in()
    addr.sin_family = sa_family_t(AF_INET)
    addr.sin_port = PORT.bigEndian
    addr.sin_addr.s_addr = inet_addr("127.0.0.1")
    let bound = withUnsafePointer(to: &addr) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) } }
    if bound != 0 { NSLog("ORBIT Hands: port in use"); exit(0) }
    listen(fd, 8)
    DispatchQueue.global().async {
        while true {
            let client = accept(fd, nil, nil)
            if client < 0 { continue }
            // Each connection on its own thread: a screenshot or status can be answered while the ball is flying.
            DispatchQueue.global().async { serveClient(client) }
        }
    }
}

func serveClient(_ client: Int32) {
            var data = Data()
            var buf = [UInt8](repeating: 0, count: 65536)
            while true {
                let n = read(client, &buf, buf.count)
                if n <= 0 { break }
                data.append(buf, count: n)
                if buf[n - 1] == 10 || data.count > 4_000_000 { break }
            }
            var reply: [String: Any] = ["ok": false, "error": "Érvénytelen kérés."]
            if let req = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                // Point first, so the user sees where it acts; then act.
                var point: CGPoint? = nil
                DispatchQueue.main.sync { point = AXIsProcessTrusted() ? pointFor(req) : nil }
                if let p = point { overlay.flyAndWait(to: p, click: ["click", "focus"].contains(req["cmd"] as? String ?? "")) }
                DispatchQueue.main.sync { reply = handle(req) }
            }
            var out = (try? JSONSerialization.data(withJSONObject: reply)) ?? Data("{}".utf8)
            out.append(10)
            _ = out.withUnsafeBytes { write(client, $0.baseAddress, out.count) }
            close(client)
}

final class Delegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ n: Notification) {
        buildKeyMap()
        statusBar = StatusBar()
        // Esc stops ORBIT's control from anywhere while it works (ORBIT's own synthetic Escape excluded).
        NSEvent.addGlobalMonitorForEvents(matching: .keyDown) { e in
            guard e.keyCode == 53, statusBar.busy else { return }
            if e.cgEvent?.getIntegerValueField(.eventSourceUserData) == ORBIT_EVENT_TAG { return }
            statusBar.stopNow()
        }
        serve()
        // Keyboard layout changes (Hungarian ↔ English) rebuild the shortcut map.
        DistributedNotificationCenter.default().addObserver(forName: NSNotification.Name(kTISNotifySelectedKeyboardInputSourceChanged as String), object: nil, queue: .main) { _ in
            keyForChar = [:]
            buildKeyMap()
        }
    }
}

let app = NSApplication.shared
let delegate = Delegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
