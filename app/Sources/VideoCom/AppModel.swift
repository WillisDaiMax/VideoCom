import AppKit
import Foundation

@MainActor
final class AppModel: ObservableObject {
    // 开始页
    @Published var line: Line = .daily
    @Published var sources: [URL] = []
    @Published var root: URL? = UserDefaults.standard.url(forKey: "batchRoot")
    /// 小于多少 MB 不用压缩，0 = 不考虑原视频大小
    @Published var minSizeMB: Double = UserDefaults.standard.double(forKey: "minSizeMB")

    // 批次
    @Published var manifest: Manifest?
    @Published var step: Step = .start
    @Published var status: [String: Any] = [:]

    // 运行状态
    @Published var busy = false
    @Published var busyTitle = ""
    @Published var progress: Double?
    @Published var progressName = ""
    @Published var errorMessage: String?
    @Published var warnings: [String] = []
    @Published var cleanupPreview: (ids: [Int], freed: Int64)?

    private var pollTask: Task<Void, Never>?

    var batchDir: String? { manifest?.batch_dir }

    /// 要压缩 + 仅转封装 的预估合计
    struct Totals { var src: Int64 = 0; var out: Int64 = 0; var seconds: Double = 0; var count = 0 }
    func totals(_ entries: [Entry]? = nil) -> Totals {
        var t = Totals()
        for e in entries ?? manifest?.entries ?? [] {
            guard let est = e.shownEstimate else { continue }
            t.src += e.size; t.out += est.out_size; t.seconds += est.seconds; t.count += 1
        }
        return t
    }

    func sorted(_ list: [Entry], by key: SortKey) -> [Entry] {
        func v(_ e: Entry) -> Double {
            switch key {
            case .value: return e.shownEstimate?.value ?? -1
            case .saved: return Double(e.shownEstimate?.saved ?? -1)
            case .size: return Double(e.size)
            case .ratio: return -(e.shownEstimate?.ratio ?? 2)     // 压缩率越低越靠前
            case .time: return -(e.shownEstimate?.seconds ?? .infinity)
            case .name: return 0
            }
        }
        if key == .name { return list.sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending } }
        return list.sorted { v($0) > v($1) }
    }
    var lastBatch: String? { UserDefaults.standard.string(forKey: "lastBatch") }

    var maxReachableStep: Step {
        switch manifest?.stage {
        case "scanned": return .review
        case "moved": return .waiting
        case "finished", "cleaned": return .results
        default: return .start
        }
    }

    // MARK: - 通用执行

    private func perform(_ title: String, _ args: [String], reload: Bool = true) async -> [String: Any]? {
        busy = true; busyTitle = title; progress = nil; progressName = ""; warnings = []
        defer { busy = false; progress = nil }
        do {
            let r = try await CoreRunner.run(args) { [weak self] ev in self?.handle(ev) }
            if reload, let dir = (r["batch"] as? String) ?? batchDir { try load(dir) }
            return r
        } catch {
            errorMessage = error.localizedDescription
            if let dir = batchDir { try? load(dir) }
            return nil
        }
    }

    private func handle(_ ev: [String: Any]) {
        switch ev["type"] as? String {
        case "progress":
            if let d = ev["done"] as? Double, let t = ev["total"] as? Double, t > 0 { progress = d / t }
            progressName = ev["name"] as? String ?? ""
        case "warn":
            if let m = ev["msg"] as? String { warnings.append(m) }
        default: break
        }
    }

    func load(_ dir: String) throws {
        let m = try CoreRunner.loadManifest(dir)
        manifest = m
        UserDefaults.standard.set(dir, forKey: "lastBatch")
        step = maxReachableStep
        if step == .waiting { startPolling() } else { stopPolling() }
    }

    // MARK: - 各步骤

    func scan() async {
        guard let root, !sources.isEmpty else { return }
        UserDefaults.standard.set(root, forKey: "batchRoot")
        UserDefaults.standard.set(minSizeMB, forKey: "minSizeMB")
        _ = await perform(T("busy.scan"), ["scan", "--line", line.rawValue, "--root", root.path,
                                      "--min-size-mb", String(max(0, minSizeMB)), "--src"] + sources.map(\.path))
    }

    func openBatch(_ dir: String) {
        do { try load(dir) } catch { errorMessage = T("err.openBatch", error.localizedDescription) }
    }

    func setBucket(ids: [Int], bucket: Bucket, subgroup: String? = nil) async {
        guard let dir = batchDir, !ids.isEmpty else { return }
        var args = ["set-bucket", "--batch", dir, "--ids", ids.map(String.init).joined(separator: ","), "--bucket", bucket.rawValue]
        if let subgroup { args += ["--subgroup", subgroup] }
        // 改分类很快，不弹遮罩，直接重载
        do {
            try await CoreRunner.run(args)
            try load(dir)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func apply() async {
        guard let dir = batchDir else { return }
        _ = await perform(T("busy.apply"), ["apply", "--batch", dir])
    }

    func refreshStatus() async {
        guard let dir = batchDir else { return }
        if let r = try? await CoreRunner.run(["status", "--batch", dir]) { status = r }
    }

    func finish() async {
        guard let dir = batchDir else { return }
        stopPolling()
        _ = await perform(T("busy.finish"), ["finish", "--batch", dir])
    }

    func undo() async {
        guard let dir = batchDir else { return }
        stopPolling()
        _ = await perform(T("busy.undo"), ["undo", "--batch", dir])
    }

    func previewCleanup(includeWarn: Bool) async {
        guard let dir = batchDir else { return }
        var args = ["cleanup", "--batch", dir]
        if includeWarn { args.append("--include-warn") }
        if let r = await perform(T("busy.cleanupPreview"), args, reload: false) {
            let ids = (r["ids"] as? [Any])?.compactMap { ($0 as? NSNumber)?.intValue } ?? []
            cleanupPreview = (ids, (r["freed"] as? NSNumber)?.int64Value ?? 0)
        }
    }

    func cleanup(includeWarn: Bool) async {
        guard let dir = batchDir, let preview = cleanupPreview, !preview.ids.isEmpty else { return }
        var args = ["cleanup", "--batch", dir, "--yes", "--ids", preview.ids.map(String.init).joined(separator: ",")]
        if includeWarn { args.append("--include-warn") }
        cleanupPreview = nil
        _ = await perform(T("busy.cleanup"), args)
    }

    func newBatch() {
        stopPolling()
        manifest = nil; sources = []; status = [:]; step = .start
    }

    // MARK: - 等待转码时自动轮询

    func startPolling() {
        guard pollTask == nil else { return }
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refreshStatus()
                try? await Task.sleep(nanoseconds: 15_000_000_000)
            }
        }
    }

    func stopPolling() {
        pollTask?.cancel(); pollTask = nil
    }

    // MARK: - Finder / 其它 App

    func reveal(_ path: String) {
        let url = URL(fileURLWithPath: path)
        if FileManager.default.fileExists(atPath: path) {
            NSWorkspace.shared.activateFileViewerSelecting([url])
        }
    }

    func openReport() {
        guard let rep = manifest?.dirs["report"] else { return }
        NSWorkspace.shared.open(URL(fileURLWithPath: rep).appendingPathComponent("report.html"))
    }

    /// 外部转码 App 的位置（找不到返回 nil，按钮就不显示）
    func appURL(for engine: String) -> URL? {
        let name = engine.replacingOccurrences(of: "external:", with: "")
        let candidates: [String]
        switch name {
        case "Aagedal": candidates = ["Aagedal Media Converter", "Aagedal Media Converter Pro", "Aagedal"]
        case "HandBrake": candidates = ["HandBrake"]
        default: candidates = [name]
        }
        for c in candidates {
            for dir in ["/Applications", NSHomeDirectory() + "/Applications"] {
                let p = "\(dir)/\(c).app"
                if FileManager.default.fileExists(atPath: p) { return URL(fileURLWithPath: p) }
            }
        }
        return nil
    }

    func pickFolders(multiple: Bool) -> [URL] {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = multiple
        panel.allowsMultipleSelection = multiple
        panel.prompt = T("common.choose")
        return panel.runModal() == .OK ? panel.urls : []
    }
}
