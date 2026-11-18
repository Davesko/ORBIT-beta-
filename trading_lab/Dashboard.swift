import SwiftUI

enum DeskPage: String, CaseIterable, Identifiable {
    case overview = "Áttekintés", portfolio = "Portfólió", trading = "Kereskedés", settings = "Beállítások"
    var id: String { rawValue }
    var icon: String {
        switch self { case .overview: return "square.grid.2x2"; case .portfolio: return "chart.pie"; case .trading: return "arrow.left.arrow.right"; case .settings: return "slider.horizontal.3" }
    }
    var subtitle: String {
        switch self {
        case .overview: return "Piacok, portfólió és automatikus AI-elemzés."
        case .portfolio: return "Miben van pénzed, és hogyan változik az értéke."
        case .trading: return "Másolás, gyors AI és folyamatos kutatás."
        case .settings: return "Működés és kockázati keret."
        }
    }
}
private func amount(_ raw: String?, digits: Int = 2) -> String {
    guard let raw else { return "—" }
    let value = NSDecimalNumber(string: raw, locale: Locale(identifier: "en_US_POSIX"))
    guard value != NSDecimalNumber.notANumber else { return "—" }
    let formatter = NumberFormatter()
    formatter.locale = Locale(identifier: "hu_HU"); formatter.numberStyle = .decimal
    formatter.minimumFractionDigits = digits; formatter.maximumFractionDigits = digits
    return formatter.string(from: value) ?? "—"
}
private func clockLabel(_ raw: String?) -> String {
    guard let raw else { return "még nincs adat" }
    let fractional = ISO8601DateFormatter(); fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    guard let date = fractional.date(from: raw) ?? ISO8601DateFormatter().date(from: raw) else { return "ismeretlen" }
    let formatter = DateFormatter(); formatter.locale = Locale(identifier: "hu_HU")
    formatter.dateFormat = "MM.dd. HH:mm:ss"; return formatter.string(from: date)
}
private func pnlColor(_ raw: String?) -> Color {
    let value = Double(raw ?? "0") ?? 0
    return value > 0 ? .green : value < 0 ? .red : .secondary
}

@MainActor final class DeskStore: ObservableObject {
    @Published var snapshot: BridgeResponse?
    @Published var busy = false
    @Published var message = "Automatikus adatgyűjtés indítása…"
    @Published var failed = false
    @Published var output = ""
    @Published var positionLimit = 50.0
    @Published var grossLimit = 100.0
    func refresh() async {
        do { snapshot = try await Task.detached { try Bridge.call("dashboard_snapshot") }.value }
        catch { snapshot = nil; failed = true; message = "Az adatállapot nem elérhető: " + error.localizedDescription }
    }
    func run(_ action: String, symbol: String = "", news: String = "") {
        guard !busy else { return }
        busy = true; failed = false; message = "Feldolgozás…"
        Task {
            do {
                let response = try await Task.detached { try Bridge.call(action, symbol: symbol, news: news) }.value
                failed = !response.ok; message = response.message
                output = response.display ?? response.message
                if let raw = response.max_position_percent, let value = Double(raw) { positionLimit = value }
                if let raw = response.max_gross_percent, let value = Double(raw) { grossLimit = value }
                await refresh()
            } catch { failed = true; message = error.localizedDescription }
            busy = false
        }
    }
    func begin() async {
        do { let response = try await Task.detached { try Bridge.call("monitor_start") }.value; message = response.message; failed = !response.ok }
        catch { failed = true; message = "Az adatgyűjtés nem indult: " + error.localizedDescription }
        do { let response = try await Task.detached { try Bridge.call("research_ensure") }.value; if !response.ok { failed = true; message = response.message } }
        catch { failed = true; message = "A kutató indítása nem sikerült: " + error.localizedDescription }
    }
}
struct DeskCard<Content: View>: View {
    let title: String, icon: String
    let content: Content
    init(_ title: String, icon: String, @ViewBuilder content: () -> Content) {
        self.title = title; self.icon = icon; self.content = content()
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label(title, systemImage: icon).font(.headline)
            content
        }.frame(maxWidth: .infinity, alignment: .leading).padding(20)
            .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 16))
            .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.primary.opacity(0.06), lineWidth: 1))
    }
}
struct BalanceCard: View {
    let summary: BridgeResponse?
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("Portfólióérték").font(.caption).foregroundStyle(.secondary)
                Spacer(); Text("VIRTUÁLIS").font(.caption2).foregroundStyle(.secondary)
            }
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text(amount(summary?.equity)).font(.system(size: 28, weight: .semibold, design: .rounded)).monospacedDigit().foregroundStyle(pnlColor(summary?.change))
                Text("USDC").font(.caption).foregroundStyle(.secondary)
            }
            Text(amount(summary?.change) + "  (" + amount(summary?.change_percent) + "%)").font(.caption).monospacedDigit().foregroundStyle(pnlColor(summary?.change))
            Text(summary?.source == "virtual_empty" ? "Szabad tesztkeret · nincs befektetve" : "Átértékelés: " + clockLabel(summary?.updated_at)).font(.caption2).foregroundStyle(.secondary)
        }.padding(16).background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 16))
    }
}
struct MarketTile: View {
    let row: MarketRow
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(row.symbol).font(.headline)
            Text(amount(row.price, digits: (Double(row.price) ?? 1) < 1 ? 5 : 2)).font(.title3).fontWeight(.semibold).monospacedDigit()
            Text(amount(row.change_percent) + "% / 24h").font(.caption).foregroundStyle(pnlColor(row.change_percent))
        }.frame(maxWidth: .infinity, alignment: .leading).padding(14)
            .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 12))
    }
}
struct NewsRowView: View {
    let item: NewsItem
    private var label: String {
        switch item.status {
        case "analyzed": return item.analysis?.impact == "positive" ? "Pozitív hatás" : item.analysis?.impact == "negative" ? "Negatív hatás" : "Bizonytalan hatás"
        case "analyzing": return "AI elemzi…"
        case "pending": return "Elemzésre vár"
        case "failed": return "Elemzési hiba"
        default: return "Korábbi / nem célzott hír"
        }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack {
                Text(item.source + " · " + clockLabel(item.published_at)).font(.caption).foregroundStyle(.secondary)
                Spacer(); Text(label).font(.caption).foregroundStyle(.secondary)
            }
            if let url = URL(string: item.url) { Link(item.title, destination: url).font(.callout).fontWeight(.medium) }
            if let evidence = item.analysis?.evidence {
                Text(evidence).font(.callout).foregroundStyle(.secondary).lineLimit(4)
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}
struct DashboardView: View {
    @StateObject private var store = DeskStore()
    @State private var selected: DeskPage? = .overview
    @State private var visibility: NavigationSplitViewVisibility = .all
    @AppStorage("publicTraderAddress") private var address = ""
    @State private var query = ""
    @State private var showAllMarkets = false
    @State private var showActivity = false
    @State private var activity = ""
    @State private var tradingMode = "copy"
    @State private var confirmClose = false
    private var page: DeskPage { selected ?? .overview }
    private var validAddress: Bool { address.range(of: "^0x[0-9a-fA-F]{40}$", options: .regularExpression) != nil }
    private var candidate: TraderCandidate? { store.snapshot?.discovery?.candidates?.first { $0.address == address } }
    private var marketRows: [MarketRow] {
        let rows = store.snapshot?.market?.rows ?? []
        if !query.isEmpty { return rows.filter { $0.symbol.localizedCaseInsensitiveContains(query) } }
        return showAllMarkets ? rows : Array(rows.prefix(8))
    }
    var body: some View {
        NavigationSplitView(columnVisibility: $visibility) {
            List(selection: $selected) {
                ForEach(DeskPage.allCases) { item in Label(item.rawValue, systemImage: item.icon).tag(item) }
            }.listStyle(.sidebar)
                .safeAreaInset(edge: .top) {
                    HStack(spacing: 10) {
                        Image(systemName: "chart.line.uptrend.xyaxis").font(.title3).foregroundStyle(.indigo)
                            .frame(width: 36, height: 36).background(Color.indigo.opacity(0.12), in: RoundedRectangle(cornerRadius: 10))
                        VStack(alignment: .leading, spacing: 3) {
                            Text("MiLLIONS").font(.headline)
                            Text("Helyi intelligencia").font(.caption).foregroundStyle(.secondary)
                        }; Spacer()
                    }.padding(16)
                }
                .safeAreaInset(edge: .bottom) {
                    VStack(alignment: .leading, spacing: 6) {
                        Label(store.snapshot?.monitor_running == true ? "Adatgyűjtés működik" : "Adatgyűjtés áll", systemImage: "circle.fill")
                            .font(.caption).foregroundStyle(store.snapshot?.monitor_running == true ? Color.green : Color.orange)
                        Text("Virtuális üzemmód").font(.caption).foregroundStyle(.secondary)
                    }.frame(maxWidth: .infinity, alignment: .leading).padding(16)
                }.navigationSplitViewColumnWidth(min: 180, ideal: 210, max: 230)
        } detail: {
            GeometryReader { geometry in
                VStack(spacing: 0) {
                    header(wide: geometry.size.width > 670).padding(geometry.size.width > 670 ? 28 : 18)
                    ScrollView { content.padding(.horizontal, geometry.size.width > 670 ? 28 : 18).padding(.bottom, 24) }
                    Divider()
                    HStack(spacing: 8) {
                        if store.busy { ProgressView().controlSize(.small) }
                        Text(store.message).font(.caption).foregroundStyle(store.failed ? Color.red : Color.secondary).lineLimit(2)
                        Spacer(minLength: 0)
                    }.padding(.horizontal, 22).padding(.vertical, 12)
                }.background(Color(nsColor: .windowBackgroundColor))
            }
        }.navigationSplitViewStyle(.balanced).tint(.indigo)
            .task {
                await store.begin()
                while !Task.isCancelled {
                    await store.refresh()
                    try? await Task.sleep(nanoseconds: 2_000_000_000)
                }
            }.onChange(of: selected) { _, value in
                store.output = ""
                if value == .settings { store.run("risk_settings") }
            }
            .onChange(of: store.snapshot?.following) { old, active in
                if old == false && active == true { selected = .portfolio }
            }
            .onChange(of: store.snapshot?.fast_running) { old, active in
                if old == false && active == true { selected = .portfolio }
            }
            .onChange(of: store.snapshot?.strategy_mode) { old, mode in
                if old == nil && mode == "fast_ai" { tradingMode = "fast_ai" }
            }
            .confirmationDialog("Minden virtuális pozíció lezárása?", isPresented: $confirmClose, titleVisibility: .visible) {
                Button("Virtuális pozíciók lezárása", role: .destructive) { store.run("paper_flatten") }
            } message: { Text("Friss piaci árakkal és szimulált díjakkal számol. Valódi megbízás nem történik.") }
    }
    private var title: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(page.rawValue).font(.system(size: 28, weight: .semibold, design: .rounded))
            Text(page.subtitle).font(.callout).foregroundStyle(.secondary)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
    @ViewBuilder private func header(wide: Bool) -> some View {
        if wide { HStack(spacing: 22) { title; BalanceCard(summary: store.snapshot).frame(width: 290) } }
        else { VStack(alignment: .leading, spacing: 16) { title; BalanceCard(summary: store.snapshot) } }
    }
    @ViewBuilder private var content: some View {
        switch page { case .overview: overview; case .portfolio: portfolio; case .trading: trading; case .settings: settings }
    }
    private var overview: some View {
        VStack(spacing: 20) {
            DeskCard("Piacok", icon: "waveform.path.ecg") {
                HStack {
                    Label(store.snapshot?.market?.fresh == true ? "Friss árfolyamok" : "Nincs friss árfolyam", systemImage: "circle.fill")
                        .font(.caption).foregroundStyle(store.snapshot?.market?.fresh == true ? Color.green : Color.orange)
                    Spacer(); Text(clockLabel(store.snapshot?.market?.updated_at)).font(.caption).foregroundStyle(.secondary)
                }
                TextField("Piac keresése…", text: $query).textFieldStyle(.roundedBorder)
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 145), spacing: 12)], spacing: 12) {
                    ForEach(marketRows) { MarketTile(row: $0) }
                }.opacity(store.snapshot?.market?.fresh == true ? 1 : 0.45)
                if let error = store.snapshot?.market?.error { Text(error).font(.caption).foregroundStyle(.orange) }
                if query.isEmpty { Button(showAllMarkets ? "Kevesebb piac" : "Összes elérhető piac") { showAllMarkets.toggle() } }
                Text("Hyperliquid fő perpetual piac · mark árak · kb. 3 másodperces lekérés. Részvénytulajdont nem mutat.")
                    .font(.caption2).foregroundStyle(.secondary)
            }
            DeskCard("Automatikus AI-figyelő", icon: "sparkles") {
                HStack {
                    Text(String(store.snapshot?.analyzed_count ?? 0) + " elemzett hír").font(.headline)
                    Spacer(); Text(String(store.snapshot?.pending_count ?? 0) + " várakozik").font(.caption).foregroundStyle(.secondary)
                }
                Text(store.snapshot?.news_fresh == true ? "Hírgyűjtés aktív · " + clockLabel(store.snapshot?.news_updated_at) : "A hírforrások frissítése nem igazolt.")
                    .font(.caption).foregroundStyle(store.snapshot?.news_fresh == true ? Color.secondary : Color.orange)
                ForEach(store.snapshot?.news_sources ?? []) { source in
                    if !source.ok { Text(source.name + ": a forrás nem elérhető").font(.caption).foregroundStyle(.orange) }
                }
                let items = Array((store.snapshot?.news_items ?? []).filter { $0.status != "archive" }.prefix(6))
                if items.isEmpty { Text("Az alkalmazás automatikusan gyűjti a híreket. Nem kell szöveget bemásolnod.").foregroundStyle(.secondary) }
                ForEach(items) { item in Divider(); NewsRowView(item: item) }
                Text("RSS-címek és kivonatok elemzése. A jelzett hatás önmagában nem belépési utasítás.").font(.caption2).foregroundStyle(.secondary)
            }
            DeskCard("Portfólió", icon: "chart.bar.xaxis") {
                HStack { Text("Nyitott pozíciók"); Spacer(); Text(String(store.snapshot?.position_count ?? 0)).font(.title2).monospacedDigit() }
                Text(store.snapshot?.fast_running == true ? "Gyors AI aktív" : store.snapshot?.following == true ? "Virtuális kereskedőkövetés aktív" : "A kereskedés szünetel").foregroundStyle(.secondary)
                if store.snapshot?.strategy_mode != "fast_ai", let error = store.snapshot?.copy_error { Text(error).font(.caption).foregroundStyle(.orange) }
                Button("Portfólió megnyitása") { selected = .portfolio }.buttonStyle(.borderedProminent)
            }
        }
    }
    private var trading: some View {
        VStack(spacing: 20) {
            Picker("Kereskedési mód", selection: $tradingMode) {
                Text("Kereskedőkövetés").tag("copy")
                Text("Gyors AI").tag("fast_ai")
                Text("Kutatás").tag("research")
            }.pickerStyle(.segmented)
            if tradingMode == "fast_ai" {
                fastPanel
            } else if tradingMode == "research" {
                researchPanel
            } else {
            DeskCard("Kereskedőválasztás", icon: "person.2") {
                let candidates = store.snapshot?.discovery?.candidates ?? []
                Picker("Adatalapú jelöltek", selection: $address) {
                    Text("Válassz kereskedőt…").tag("")
                    ForEach(candidates) { person in
                        Text(person.name + " · " + amount(person.return_percent) + "% / hó (becslés)").tag(person.address)
                    }
                    if !address.isEmpty && candidate == nil { Text("Saját cím: " + address.prefix(10) + "…").tag(address) }
                }.pickerStyle(.menu).disabled(store.snapshot?.following == true)
                if let person = candidate {
                    HStack { Text("Havi PnL"); Spacer(); Text(amount(person.pnl_month) + " USDC").foregroundStyle(.green) }
                    HStack { Text("Becsült legnagyobb visszaesés"); Spacer(); Text(amount(person.drawdown_percent) + "%") }
                    HStack { Text("Jelenlegi kitettség"); Spacer(); Text(amount(person.gross_percent) + "%") }
                    Text(String(person.days) + " nap megfigyelt múlt · " + person.address).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                }
                if candidates.isEmpty { Text(store.snapshot?.discovery?.updated_at == nil || store.snapshot?.discovery?.searching == true ? "Jelöltek keresése és múltbeli adataik ellenőrzése…" : "Most nincs a feltételeknek megfelelő jelölt.").foregroundStyle(.secondary) }
                if store.snapshot?.discovery?.searching == true { Text("Ellenőrzött számlák: " + String(store.snapshot?.discovery?.checked ?? 0)).font(.caption).foregroundStyle(.secondary) }
                if let error = store.snapshot?.discovery?.error { Text(error).font(.caption).foregroundStyle(.orange) }
                if store.snapshot?.discovery?.fresh != true && !candidates.isEmpty { Text("A jelöltlista elavult; új követés innen nem indítható.").font(.caption).foregroundStyle(.orange) }
                Text("Ellenőrizve: " + clockLabel(store.snapshot?.discovery?.updated_at) + " · óránként új keresés").font(.caption).foregroundStyle(.secondary)
                DisclosureGroup("Kiválasztási szempontok") {
                    Text(store.snapshot?.discovery?.method ?? "Legalább 25 nap megfigyelt múlt, pozitív heti és havi eredmény, korlátozott visszaesés és kitettség. A múltbeli eredmény nem garantál hozamot.").font(.caption).foregroundStyle(.secondary)
                }
                DisclosureGroup("Saját nyilvános számlacím") {
                    TextField("0x…", text: $address).textFieldStyle(.roundedBorder).disabled(store.snapshot?.following == true)
                    Text("Csak nyilvános cím; a fő Hyperliquid perpetual piacot figyeli.").font(.caption).foregroundStyle(.secondary)
                }
                ViewThatFits(in: .horizontal) {
                    HStack { startButton; pauseButton }
                    VStack(alignment: .leading, spacing: 10) { startButton; pauseButton }
                }
                Text("10 000 virtuális USDC · meglévő pozíciók felvételével · nincs valódi megbízás.").font(.caption).foregroundStyle(.secondary)
            }
            DeskCard("Követés és pozíciók", icon: "arrow.triangle.2.circlepath") {
                Text(store.snapshot?.following == true ? "Folyamatos virtuális követés" : "Követés szünetel").font(.headline)
                Text("Utolsó követési ciklus: " + clockLabel(store.snapshot?.copy_updated_at)).font(.caption).foregroundStyle(.secondary)
                if let leader = store.snapshot?.followed_address { Text(leader).font(.caption).foregroundStyle(.secondary).textSelection(.enabled) }
                if let error = store.snapshot?.copy_error { Text(error).foregroundStyle(.orange) }
                Button("Teljes portfólió") { selected = .portfolio }
                Text("Nyitott virtuális pozíciók: " + String(store.snapshot?.position_count ?? 0)).foregroundStyle(.secondary)
            }
            }
        }
    }

    private var fastPanel: some View {
        VStack(spacing: 20) {
            DeskCard("Gyors AI · virtuális teszt", icon: "bolt") {
                Text("Rövid ügyletek, automatikus kiszállással").font(.title3).fontWeight(.semibold)
                Text("A helyi AI az aktuális ármozgást, forgalmat és a friss hírkivonatokat vizsgálja. A bekötött piac nagy forgalmú memecoinjai is bekerülhetnek.").foregroundStyle(.secondary)
                HStack { Text("Egy ügylet mérete"); Spacer(); Text("legfeljebb a tőke 10%-a") }
                HStack { Text("Ármozgási veszteségküszöb"); Spacer(); Text("−0,75%") }
                HStack { Text("Ármozgási nyereségcél"); Spacer(); Text("+1,50%") }
                HStack { Text("Időkorlát"); Spacer(); Text("3 perc") }
                Text("Egyszerre egy pozíció · legfeljebb 6 nyitás óránként · 2% napi veszteségkorlát · díjak és csúszás szimulálva.").font(.caption).foregroundStyle(.secondary)
                if store.snapshot?.following == true {
                    Text("Most kereskedőkövetés fut. Módváltáshoz szüneteltesd, és zárd le a virtuális pozíciókat a Portfólió oldalon.").font(.caption).foregroundStyle(.orange)
                    Button("Portfólió megnyitása") { selected = .portfolio }
                }
                ViewThatFits(in: .horizontal) {
                    HStack { fastStart; fastPause }
                    VStack(alignment: .leading, spacing: 10) { fastStart; fastPause }
                }
                Text("Nincs milliszekundumos előny vagy igazolt nyereségesség. A kiszállás friss ár elérhetőségéhez kötött; az árugrás és a kapcsolat hibája növelheti a veszteséget.").font(.caption).foregroundStyle(.secondary)
            }
            DeskCard("AI-kutatás és működés", icon: "sparkles") {
                Text(store.snapshot?.fast_message ?? "A gyors mód még nem indult el.").font(.headline)
                if let reason = store.snapshot?.fast_research { Text(reason).foregroundStyle(.secondary) }
                if let error = store.snapshot?.fast_error { Text(error).font(.caption).foregroundStyle(.orange) }
                Button("Nyitott ügyletek a Portfólióban") { selected = .portfolio }
            }
        }
    }

    private var researchPanel: some View {
        ResearchPanel(snapshot: store.snapshot, busy: store.busy) { store.run($0) }
    }
    private var fastStart: some View {
        Button("Gyors AI indítása") { store.run("fast_start") }.buttonStyle(.borderedProminent)
            .disabled(store.busy || store.snapshot?.following == true || store.snapshot?.fast_running == true)
    }
    private var fastPause: some View {
        Button("Gyors AI szüneteltetése") { store.run("fast_stop") }.disabled(store.busy || store.snapshot?.fast_running != true)
    }

    private var portfolio: some View {
        VStack(spacing: 20) {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 190), spacing: 16)], spacing: 16) {
                DeskCard("Elszámolt egyenleg", icon: "banknote") {
                    Text(amount(store.snapshot?.settled_balance) + " USDC").font(.title3).fontWeight(.semibold).monospacedDigit()
                    Text("Lezárt eredménnyel és díjakkal").font(.caption).foregroundStyle(.secondary)
                }
                DeskCard("Nyitott eredmény", icon: "chart.line.uptrend.xyaxis") {
                    Text(amount(store.snapshot?.unrealized_pnl) + " USDC").font(.title3).fontWeight(.semibold).monospacedDigit().foregroundStyle(pnlColor(store.snapshot?.unrealized_pnl))
                    Text("A jelenlegi pozíciók változása").font(.caption).foregroundStyle(.secondary)
                }
                DeskCard("Szabad nyitási keret", icon: "plus.circle") {
                    Text(amount(store.snapshot?.available_capacity) + " USDC").font(.title3).fontWeight(.semibold).monospacedDigit()
                    Text("A virtuális kitettségi korlát szerint").font(.caption).foregroundStyle(.secondary)
                }
            }
            DeskCard("Eszközeim", icon: "chart.pie") {
                HStack {
                    Text("Összes nyitott kitettség").foregroundStyle(.secondary)
                    Spacer(); Text(amount(store.snapshot?.gross_exposure) + " USDC").fontWeight(.semibold).monospacedDigit()
                }
                Text("A kitettség a határidős pozíció piaci mérete. A saját pénzed összegét a felső portfólióérték mutatja.").font(.caption).foregroundStyle(.secondary)
                if (Double(store.snapshot?.capacity_deficit ?? "0") ?? 0) > 0 {
                    Text("A jelenlegi kitettség túllépi az új nyitásokra beállított keretet.").font(.caption).foregroundStyle(.orange)
                }
                if (store.snapshot?.paper_positions ?? []).isEmpty {
                    ContentUnavailableView(store.snapshot?.valuation_complete == true ? "Még nincs nyitott pozíció" : "A portfólióadat nem elérhető", systemImage: "chart.pie", description: Text("A megnyitott virtuális ügyletek automatikusan megjelennek itt."))
                    Button("Kereskedés megnyitása") { selected = .trading }.buttonStyle(.borderedProminent)
                }
                ForEach(store.snapshot?.paper_positions ?? []) { position in
                    Divider()
                    PortfolioPositionView(position: position)
                }
            }
            DeskCard("Működés", icon: "arrow.triangle.2.circlepath") {
                Text(store.snapshot?.strategy_mode == "fast_ai" ? (store.snapshot?.fast_running == true ? "Gyors AI aktív" : "Gyors AI szünetel") : (store.snapshot?.following == true ? "Kereskedőkövetés aktív" : "Kereskedőkövetés szünetel")).font(.headline)
                if let leader = store.snapshot?.followed_address {
                    Text("Követett számla: " + leader).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                }
                if store.snapshot?.strategy_mode == "fast_ai" {
                    if let message = store.snapshot?.fast_message { Text(message).font(.caption).foregroundStyle(.secondary) }
                    if let error = store.snapshot?.fast_error { Text(error).font(.caption).foregroundStyle(.orange) }
                } else if let error = store.snapshot?.copy_error { Text(error).font(.caption).foregroundStyle(.orange) }
                Text("Árfolyamok: " + clockLabel(store.snapshot?.market?.updated_at)).font(.caption).foregroundStyle(.secondary)
                HStack {
                    Button("Kereskedés szüneteltetése") { store.run(store.snapshot?.strategy_mode == "fast_ai" ? "fast_stop" : "paper_stop") }
                        .disabled(store.busy || (store.snapshot?.following != true && store.snapshot?.fast_running != true))
                    Button("Pozíciók lezárása", role: .destructive) { confirmClose = true }
                        .disabled(store.busy || store.snapshot?.following == true || store.snapshot?.fast_running == true || (store.snapshot?.position_count ?? 0) == 0)
                }
            }
        }
    }
    private var startButton: some View {
        Button("Virtuális követés indítása") { store.run("paper_start", symbol: address) }.buttonStyle(.borderedProminent)
            .disabled(!validAddress || store.busy || store.snapshot?.following == true || (candidate != nil && store.snapshot?.discovery?.fresh != true))
    }
    private var pauseButton: some View {
        Button("Szüneteltetés") { store.run("paper_stop") }.disabled(store.busy || store.snapshot?.following != true)
    }
    private var settings: some View {
        VStack(spacing: 20) {
            DeskCard("Folyamatos működés", icon: "power") {
                HStack {
                    Button("Adatgyűjtés indítása") { store.run("monitor_start") }
                    Button("Adatgyűjtés szüneteltetése") { store.run("monitor_stop") }
                }.disabled(store.busy)
                HStack {
                    Button("Helyi AI indítása") { store.run("start") }
                    Button("Helyi AI leállítása") { store.run("stop") }
                }.disabled(store.busy)
                Text("A gyűjtő az ablak bezárása után is fut. Az alkalmazás megnyitásakor újra elindul. A Macnek bekapcsolva és ébren kell maradnia. A kereskedőkövetés külön szüneteltethető.").font(.caption).foregroundStyle(.secondary)
                ForEach(store.snapshot?.news_sources ?? []) { source in
                    Label(source.name + (source.ok ? " · elérhető" : " · kapcsolati hiba"), systemImage: source.ok ? "checkmark.circle" : "exclamationmark.circle")
                        .font(.caption).foregroundStyle(source.ok ? Color.secondary : Color.orange)
                }
            }
            DeskCard("Virtuális kockázati keret", icon: "shield") {
                HStack { Text("Pozíciónként"); Spacer(); Text(String(format: "%.0f%%", store.positionLimit)) }
                Slider(value: $store.positionLimit, in: 1...100, step: 1).disabled(store.busy)
                HStack { Text("Összesített kitettség"); Spacer(); Text(String(format: "%.0f%%", store.grossLimit)) }
                Slider(value: $store.grossLimit, in: 1...100, step: 1).disabled(store.busy)
                Button("Korlátok mentése") {
                    let settings = ["max_position_percent": String(Int(store.positionLimit)), "max_gross_percent": String(Int(store.grossLimit))]
                    if let data = try? JSONSerialization.data(withJSONObject: settings), let value = String(data: data, encoding: .utf8) { store.run("save_risk", news: value) }
                }.buttonStyle(.borderedProminent).disabled(store.busy || store.positionLimit > store.grossLimit)
                Text("Új nyitást a korlát blokkolhat. Meglévő pozíciót a korlát módosítása nem zár automatikusan.").font(.caption).foregroundStyle(.secondary)
            }
            DisclosureGroup("Eseménynapló és részletek", isExpanded: $showActivity) {
                Button("Napló betöltése") { store.run("activity") }.disabled(store.busy)
                Text(store.output).font(.callout).textSelection(.enabled)
                Text("Helyi Qwen3.8-27B · éles számla nincs csatlakoztatva · Quiver hozzáférés nincs megadva.").font(.caption).foregroundStyle(.secondary)
            }.padding(8)
        }
    }
}

struct PortfolioPositionView: View {
    let position: PaperPosition
    private func field(_ title: String, _ value: String, color: Color = .primary) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.callout).fontWeight(.medium).monospacedDigit().foregroundStyle(color)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text(position.symbol).font(.title3).fontWeight(.semibold)
                Text(position.direction == "short" ? "SHORT" : "LONG").font(.caption2).fontWeight(.medium).padding(.horizontal, 7).padding(.vertical, 4).background(Color.indigo.opacity(0.12), in: Capsule())
                Spacer()
                Text(position.strategy == "news_ai" ? "Gyors AI" : "Kereskedőkövetés").font(.caption).foregroundStyle(.secondary)
            }
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 16)], alignment: .leading, spacing: 16) {
                field("Pozícióérték · kitettség", amount(position.notional) + " USDC")
                field("Nyereség / veszteség", amount(position.unrealized_pnl) + " USDC", color: pnlColor(position.unrealized_pnl))
                field("Mennyiség", amount(position.quantity, digits: 8))
                field("Aktuális ár", amount(position.price, digits: (Double(position.price ?? "1") ?? 1) < 1 ? 5 : 2))
                field("Belépési átlagár", amount(position.entry, digits: (Double(position.entry) ?? 1) < 1 ? 5 : 2))
                field("Árváltozásból eredő hozam", amount(position.pnl_percent) + "%", color: pnlColor(position.pnl_percent))
            }
            if let percent = position.exposure_percent, let fraction = Double(percent) {
                HStack {
                    Text("A nyitott kitettség " + amount(percent) + "%-a").font(.caption).foregroundStyle(.secondary)
                    Spacer(); Text("Tőkearány: " + amount(position.equity_percent) + "%").font(.caption).foregroundStyle(.secondary)
                }
                ProgressView(value: min(1, max(0, fraction / 100))).tint(.indigo)
            }
            if let error = position.error { Text(error).font(.caption).foregroundStyle(.orange) }
        }.padding(.vertical, 6)
    }
}

struct ResearchPanel: View {
    let snapshot: BridgeResponse?
    let busy: Bool
    let action: (String) -> Void
    private var state: ResearchState? { snapshot?.research }
    private var candidate: ResearchCandidate? { state?.candidate_summary }
    private func metric(_ label: String, _ value: String, color: Color = .primary) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.title3).fontWeight(.semibold).monospacedDigit().foregroundStyle(color)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
    var body: some View {
        VStack(spacing: 20) {
            DeskCard("Folyamatos AI-kutató", icon: "brain") {
                HStack {
                    Label(snapshot?.research_running == true ? "Kutató működik" : "Kutató szünetel", systemImage: "circle.fill")
                        .font(.caption).foregroundStyle(snapshot?.research_running == true ? Color.green : Color.orange)
                    Spacer(); Text(clockLabel(state?.updated_at)).font(.caption).foregroundStyle(.secondary)
                }
                Text(state?.status ?? "Kutatási adatok gyűjtése…").font(.title3).fontWeight(.semibold)
                Text(state?.phase ?? "A kutató újraindítás után a mentett eredményekből folytatja.").foregroundStyle(.secondary)
                HStack {
                    Button("Kutatás folytatása") { action("research_start") }.buttonStyle(.borderedProminent).disabled(busy || snapshot?.research_running == true)
                    Button("Szüneteltetés") { action("research_stop") }.disabled(busy || snapshot?.research_running != true)
                }
                Text("Új adatokkal újra értékel, és kedvező jelölt mellett is tovább vizsgálódik. Bekapcsolt, ébren lévő Mac szükséges.").font(.caption).foregroundStyle(.secondary)
                if let error = state?.error { Text(error).font(.caption).foregroundStyle(.orange) }
                ForEach(state?.data_errors ?? [], id: \.self) { Text($0).font(.caption).foregroundStyle(.orange) }
            }
            DeskCard("Stratégia-ellenőrzés", icon: "chart.bar.doc.horizontal") {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 170), spacing: 18)], alignment: .leading, spacing: 18) {
                    metric("Lezárt gyertyák", amount(String(state?.candles ?? 0), digits: 0))
                    metric("Rögzített napi jelöltek", String(state?.trial_count ?? 0))
                    metric("Változatok piaconként", String(state?.parameter_variants ?? 24))
                    metric("Jelölt adatmúltja", amount(candidate?.history_days.map { String($0) }) + " nap")
                    metric("Elkülönített teszt nettója", amount(candidate?.test_net_percent.map { String($0) }) + "%", color: pnlColor(candidate?.test_net_percent.map { String($0) }))
                    metric("Új adatok nettója", amount(candidate?.forward_net_percent.map { String($0) }) + "%", color: pnlColor(candidate?.forward_net_percent.map { String($0) }))
                }
                if let id = candidate?.candidate {
                    Text("Vizsgált jelölt: " + String(id.split(separator: "/").first ?? "") + (id.contains("reversion") ? " · visszatérési stratégia" : " · ármozgáskövető stratégia")).font(.caption).foregroundStyle(.secondary)
                    Text("Új adaton megfigyelt idő: " + amount(candidate?.forward_days.map { String($0) }) + " nap · lezárt ügyletek: " + String(candidate?.forward_trades ?? 0)).font(.caption).foregroundStyle(.secondary)
                }
                DisclosureGroup("Mely feltételek hiányoznak?") {
                    ForEach(candidate?.reasons ?? ["A történelmi adatok és az első teszt még készülnek."], id: \.self) {
                        Text("• " + $0).font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                Text("A fenti eredmények elkülönített kutatási szimulációk. A kutató a meglévő kereskedésed mellett dolgozik; a kedvező teszt sem garantál jövőbeli nyereséget.").font(.caption).foregroundStyle(.secondary)
            }
            DeskCard("Technológiai fejlesztések", icon: "wrench.and.screwdriver") {
                if let benchmark = state?.technology?.benchmark {
                    Text("Kutatói adatlekérés: " + (benchmark.selected == "persistent" ? "tartós HTTPS kapcsolat" : "szokásos HTTPS kapcsolat")).font(.callout).fontWeight(.medium)
                    Text("Mért medián: szokásos " + amount(benchmark.median_ms?.standard.map { String($0) }) + " ms · tartós " + amount(benchmark.median_ms?.persistent.map { String($0) }) + " ms").font(.caption).foregroundStyle(.secondary)
                }
                if let plan = state?.ai_plan {
                    Text(plan.technology_proposal ?? "").font(.callout)
                    Text("Ellenőrzési terv: " + (plan.validation_test ?? "")).font(.caption).foregroundStyle(.secondary)
                    DisclosureGroup("AI kutatási indoklás") { Text(plan.reason ?? "").font(.caption).foregroundStyle(.secondary) }
                }
                if let error = state?.ai_error { Text("AI-terv nem elérhető; a rögzített tesztek folytatódnak. " + error).font(.caption).foregroundStyle(.orange) }
                DisclosureGroup("Figyelt hivatalos kiadások") {
                    ForEach(state?.technology?.releases ?? []) { release in
                        HStack {
                            if let raw = release.url, let url = URL(string: raw) { Link(release.repository, destination: url) }
                            else { Text(release.repository) }
                            Spacer(); Text(release.version ?? "nem elérhető").foregroundStyle(.secondary)
                        }.font(.caption)
                    }
                }
                Text("Az adatlekérési mérés a kutató saját gyűjtését javítja. A további alkalmazásmódosításokat ellenőrzési tervvel ellátott javaslatként menti.").font(.caption).foregroundStyle(.secondary)
            }
        }
    }
}
