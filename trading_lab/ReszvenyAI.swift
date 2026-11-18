import SwiftUI
import AppKit

struct MarketRow: Decodable, Identifiable {
    let symbol: String
    let price: String
    let change_percent: String
    let volume: String
    var id: String { symbol }
}
struct MarketState: Decodable {
    let updated_at: String?
    let rows: [MarketRow]?
    let error: String?
    let fresh: Bool?
}
struct TraderCandidate: Decodable, Identifiable {
    let address: String
    let name: String
    let pnl_month: String
    let return_percent: String
    let drawdown_percent: String
    let equity: String
    let gross_percent: String
    let days: Int
    var id: String { address }
}
struct DiscoveryState: Decodable {
    let updated_at: String?
    let candidates: [TraderCandidate]?
    let checked: Int?
    let error: String?
    let fresh: Bool?
    let method: String?
    let searching: Bool?
}
struct NewsAnalysis: Decodable {
    let impact: String?
    let evidence: String?
    let error: String?
}
struct NewsItem: Decodable, Identifiable {
    let id: String
    let source: String
    let title: String
    let url: String
    let published_at: String
    let assets: [String]
    let status: String
    let analysis: NewsAnalysis?
}
struct NewsSource: Decodable, Identifiable {
    let name: String
    let ok: Bool
    let error: String?
    var id: String { name }
}
struct PaperPosition: Decodable, Identifiable {
    let instrument: String
    let symbol: String
    let quantity: String
    let entry: String
    let direction: String?
    let strategy: String?
    let price: String?
    let notional: String?
    let unrealized_pnl: String?
    let pnl_percent: String?
    let equity_percent: String?
    let exposure_percent: String?
    let error: String?
    var id: String { instrument }
}
struct ResearchCandidate: Decodable {
    let candidate: String?
    let history_days: Double?
    let test_net_percent: Double?
    let test_trades: Int?
    let forward_net_percent: Double?
    let forward_trades: Int?
    let forward_days: Double?
    let reasons: [String]?
    let selection_trials: Int?
}
struct ResearchPlan: Decodable {
    let reason: String?
    let technology_proposal: String?
    let validation_test: String?
}
struct ResearchRelease: Decodable, Identifiable {
    let repository: String
    let version: String?
    let url: String?
    let error: String?
    var id: String { repository }
}
struct TransportMedians: Decodable { let standard: Double?; let persistent: Double? }
struct ResearchBenchmark: Decodable {
    let selected: String?
    let median_ms: TransportMedians?
    let error: String?
}
struct ResearchTechnology: Decodable {
    let releases: [ResearchRelease]?
    let benchmark: ResearchBenchmark?
}
struct ResearchState: Decodable {
    let phase: String?
    let status: String?
    let updated_at: String?
    let error: String?
    let candles: Int?
    let trial_count: Int?
    let parameter_variants: Int?
    let eligible_count: Int?
    let data_errors: [String]?
    let candidate_summary: ResearchCandidate?
    let ai_plan: ResearchPlan?
    let ai_error: String?
    let technology: ResearchTechnology?
}
struct BridgeResponse: Decodable {
    let ok: Bool
    let message: String
    let display: String?
    let elapsed_seconds: Double?
    let model_installed: Bool?
    let version: String?
    let equity: String?
    let change: String?
    let change_percent: String?
    let currency: String?
    let source: String?
    let position_count: Int?
    let real_account_connected: Bool?
    let updated_at: String?
    let max_position_percent: String?
    let max_gross_percent: String?
    let market: MarketState?
    let discovery: DiscoveryState?
    let news_items: [NewsItem]?
    let news_sources: [NewsSource]?
    let news_updated_at: String?
    let news_fresh: Bool?
    let analyzed_count: Int?
    let pending_count: Int?
    let monitor_running: Bool?
    let following: Bool?
    let copy_error: String?
    let copy_updated_at: String?
    let paper_positions: [PaperPosition]?
    let followed_address: String?
    let settled_balance: String?
    let unrealized_pnl: String?
    let gross_exposure: String?
    let available_capacity: String?
    let capacity_deficit: String?
    let valuation_complete: Bool?
    let strategy_mode: String?
    let fast_running: Bool?
    let fast_message: String?
    let fast_research: String?
    let fast_error: String?
    let research: ResearchState?
    let research_running: Bool?
}

enum Bridge {
    static func call(_ action: String, symbol: String = "", news: String = "") throws -> BridgeResponse {
        let root = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/ReszvenyAI/core")
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.arguments = [root.appendingPathComponent("ui_bridge.py").path]
        process.currentDirectoryURL = root
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        process.environment = environment
        let input = Pipe(), output = Pipe()
        process.standardInput = input; process.standardOutput = output
        process.standardError = FileHandle.nullDevice
        try process.run()
        input.fileHandleForWriting.write(try JSONSerialization.data(withJSONObject: ["action": action, "symbol": symbol, "news": news]))
        try input.fileHandleForWriting.close()
        let data = output.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        guard process.terminationStatus == 0 else {
            throw NSError(domain: "MiLLIONS", code: 1, userInfo: [NSLocalizedDescriptionKey: "A helyi program nem indult el."])
        }
        return try JSONDecoder().decode(BridgeResponse.self, from: data)
    }
}

final class ApplicationDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApplication.shared.setActivationPolicy(.regular)
        NSApplication.shared.activate(ignoringOtherApps: true)
    }
}
#if !ORBIT_APP
@main struct MiLLIONSApp: App {
    @NSApplicationDelegateAdaptor(ApplicationDelegate.self) var delegate
    var body: some Scene {
        WindowGroup("MiLLIONS") { DashboardView().frame(minWidth: 640, minHeight: 620) }
    }
}
#endif
