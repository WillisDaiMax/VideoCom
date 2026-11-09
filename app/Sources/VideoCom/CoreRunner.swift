import Foundation

/// 调用 Python core：python3 -m videocom --events <命令>，逐行读取 JSON 事件。
/// core 位置优先级：环境变量 VIDEOCOM_CORE > .app 内 Resources/core > Info.plist 的 VideoComCorePath。
enum CoreRunner {
    struct Failure: LocalizedError {
        let message: String
        var errorDescription: String? { message }
    }

    static let searchPaths = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]

    static var python: String? {
        for d in searchPaths {
            let p = "\(d)/python3"
            if FileManager.default.isExecutableFile(atPath: p) { return p }
        }
        return nil
    }

    static var coreDir: String? {
        let fm = FileManager.default
        var candidates: [String] = []
        if let env = ProcessInfo.processInfo.environment["VIDEOCOM_CORE"] { candidates.append(env) }
        if let res = Bundle.main.resourceURL?.appendingPathComponent("core").path { candidates.append(res) }
        if let plist = Bundle.main.object(forInfoDictionaryKey: "VideoComCorePath") as? String { candidates.append(plist) }
        return candidates.first { fm.fileExists(atPath: "\($0)/videocom/__init__.py") }
    }

    /// 运行一条命令。onEvent 在主线程收到每个事件；返回最后一个 result 事件。
    @discardableResult
    static func run(_ args: [String], onEvent: @escaping @MainActor ([String: Any]) -> Void = { _ in }) async throws -> [String: Any] {
        guard let py = python else { throw Failure(message: T("err.noPython")) }
        guard let core = coreDir else { throw Failure(message: T("err.noCore")) }

        let p = Process()
        p.executableURL = URL(fileURLWithPath: py)
        p.arguments = ["-m", "videocom", "--events"] + args
        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"] = core
        env["PYTHONUNBUFFERED"] = "1"
        env["PATH"] = (searchPaths + [env["PATH"] ?? ""]).joined(separator: ":")   // Finder 启动的 App 没有 Homebrew PATH
        p.environment = env
        let out = Pipe(), err = Pipe()
        p.standardOutput = out
        p.standardError = err
        try p.run()

        var result: [String: Any] = [:]
        var errorMsg: String?
        for try await line in out.fileHandleForReading.bytes.lines {
            guard let data = line.data(using: .utf8),
                  let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { continue }
            let type = obj["type"] as? String
            if type == "result" { result = obj }
            if type == "error" { errorMsg = obj["msg"] as? String }
            await onEvent(obj)
        }
        p.waitUntilExit()
        if p.terminationStatus != 0 {
            let stderr = String(data: err.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
            throw Failure(message: errorMsg ?? (stderr.isEmpty ? T("err.exit", p.terminationStatus) : String(stderr.suffix(600))))
        }
        return result
    }

    static func loadManifest(_ batchDir: String) throws -> Manifest {
        let url = URL(fileURLWithPath: batchDir).appendingPathComponent("videocom.json")
        return try JSONDecoder().decode(Manifest.self, from: Data(contentsOf: url))
    }
}
