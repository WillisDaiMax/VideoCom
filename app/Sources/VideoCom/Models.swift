import Foundation
import SwiftUI

// 与 core 的 videocom.json 对应。只声明界面用到的字段，其余忽略。

struct Manifest: Decodable {
    var line: String
    var stage: String
    var batch_dir: String
    var dirs: [String: String]
    var engine: [String: String]
    var entries: [Entry]
}

struct Probe: Decodable, Hashable {
    var codec: String?
    var width: Int?
    var height: Int?
    var duration: Double?
    var size: Int64?
    var hdr: String?

    var resolution: String {
        guard let w = width, let h = height else { return "" }
        return "\(w)×\(h)"
    }
}

struct Check: Decodable, Hashable {
    var ok: Bool?
    var level: String
    var detail: String
}

/// core 的 estimate.py 结果
struct Estimate: Decodable, Hashable {
    var out_size: Int64
    var seconds: Double
    var ratio: Double?
    var saved: Int64
    var value: Double          // MB / 分钟
    var calibrated: Bool?
}

/// 原因代码 + 参数，界面按语言翻译（参数值统一转成字符串）
struct ReasonCode: Decodable, Hashable {
    var k: String
    var p: [String: String]

    enum CodingKeys: String, CodingKey { case k, p }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        k = try c.decode(String.self, forKey: .k)
        p = [:]
        if let raw = try? c.decode([String: AnyJSON].self, forKey: .p) {
            for (key, v) in raw { p[key] = v.text }
        }
    }
}

/// 任意 JSON 标量
struct AnyJSON: Decodable, Hashable {
    var text: String
    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if let s = try? c.decode(String.self) { text = s }
        else if let i = try? c.decode(Int.self) { text = String(i) }
        else if let d = try? c.decode(Double.self) { text = String(d) }
        else if let b = try? c.decode(Bool.self) { text = String(b) }
        else { text = "" }
    }
}

struct Entry: Decodable, Identifiable, Hashable {
    var id: Int
    var name: String
    var bucket: String
    var subgroup: String?
    var state: String
    var tags: [String]
    var reasons: [String]
    var reason_codes: [ReasonCode]?
    var notes: [String]
    var src_now: String
    var src_orig: String
    var output: String?
    var probe: Probe?
    var out_probe: Probe?
    var checks: [String: Check]
    var has_warn: Bool?
    var estimate: Estimate?

    var size: Int64 { probe?.size ?? 0 }
    var outSize: Int64? { out_probe?.size }
    var actualRatio: Double? {
        guard let b = outSize, size > 0 else { return nil }
        return Double(b) / Double(size)
    }
    /// 只有要压缩 / 仅转封装才显示预估
    var shownEstimate: Estimate? { (bucket == "compress" || bucket == "remux") ? estimate : nil }
    var failures: [(String, String)] {
        checks.filter { $0.value.level == "fail" && $0.value.ok == false }.map { ($0.key, $0.value.detail) }.sorted { $0.0 < $1.0 }
    }
    var warnings: [(String, String)] {
        checks.filter { $0.value.level == "warn" && $0.value.ok == false }.map { ($0.key, $0.value.detail) }.sorted { $0.0 < $1.0 }
    }
    var isAnomaly: Bool { state == "failed" || state == "unmatched" }

    static func == (a: Entry, b: Entry) -> Bool { a.id == b.id && a.bucket == b.bucket && a.state == b.state }
    func hash(into h: inout Hasher) { h.combine(id); h.combine(bucket); h.combine(state) }
}

enum Line: String, CaseIterable, Identifiable {
    case daily, movie
    var id: String { rawValue }
    var title: String { T(self == .daily ? "line.daily" : "line.movie") }
    var subtitle: String { T(self == .daily ? "line.daily.sub" : "line.movie.sub") }
    var icon: String { self == .daily ? "iphone" : "film" }
}

enum Bucket: String, CaseIterable, Identifiable {
    case compress, skip, review, remux
    var id: String { rawValue }
    var title: String { T("bucket.\(rawValue)") }
    var color: Color { Palette.bucket(self) }
    var icon: String {
        switch self {
        case .compress: return "arrow.down.right.and.arrow.up.left"
        case .skip: return "checkmark.circle"
        case .review: return "exclamationmark.triangle"
        case .remux: return "shippingbox"
        }
    }
}

enum Step: Int, CaseIterable, Identifiable {
    case start, review, waiting, results
    var id: Int { rawValue }
    var title: String { T(["step.start", "step.review", "step.waiting", "step.results"][rawValue]) }
    var icon: String {
        switch self {
        case .start: return "plus.square.on.square"
        case .review: return "list.bullet.rectangle"
        case .waiting: return "hourglass"
        case .results: return "chart.bar.doc.horizontal"
        }
    }
}

enum SortKey: String, CaseIterable, Identifiable {
    case value, saved, size, ratio, time, name
    var id: String { rawValue }
    var title: String { T("sort.\(rawValue)") }
}
