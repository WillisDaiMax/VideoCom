import AppKit
import SwiftUI

/// 偏好设置：语言、外观。保存在 UserDefaults。
final class Prefs: ObservableObject {
    static let shared = Prefs()

    @Published var language: Lang {
        didSet { UserDefaults.standard.set(language.rawValue, forKey: "language") }
    }
    @Published var appearance: Appearance {
        didSet {
            UserDefaults.standard.set(appearance.rawValue, forKey: "appearance")
            NSApp?.appearance = appearance.nsAppearance
        }
    }

    private init() {
        language = Lang(rawValue: UserDefaults.standard.string(forKey: "language") ?? "") ?? .system
        appearance = Appearance(rawValue: UserDefaults.standard.string(forKey: "appearance") ?? "") ?? .system
    }

    /// 实际使用的语言（跟随系统时按系统首选语言）
    var resolved: Lang {
        if language != .system { return language }
        let pref = (Locale.preferredLanguages.first ?? "en").lowercased()
        if pref.hasPrefix("zh-hant") || pref.hasPrefix("zh-tw") || pref.hasPrefix("zh-hk") || pref.hasPrefix("zh-mo") { return .zhHant }
        if pref.hasPrefix("zh") { return .zhHans }
        if pref.hasPrefix("ja") { return .ja }
        return .en
    }
}

enum Lang: String, CaseIterable, Identifiable {
    case system, zhHans = "zh-Hans", zhHant = "zh-Hant", en, ja
    var id: String { rawValue }
    /// 菜单里的名字（各用自己的语言写）
    var nativeName: String {
        switch self {
        case .system: return T("lang.system")
        case .zhHans: return "简体中文"
        case .zhHant: return "繁體中文（台灣）"
        case .en: return "English"
        case .ja: return "日本語"
        }
    }
    var index: Int {
        switch self {
        case .zhHans, .system: return 0
        case .zhHant: return 1
        case .en: return 2
        case .ja: return 3
        }
    }
}

/// 取字符串。参数用 {0} {1} … 占位。
func T(_ key: String, _ args: Any...) -> String {
    let i = Prefs.shared.resolved.index
    var s = Strings.table[key]?[i] ?? Strings.table[key]?[2] ?? key
    for (n, a) in args.enumerated() { s = s.replacingOccurrences(of: "{\(n)}", with: "\(a)") }
    return s
}

/// core 返回的原因代码 → 当前语言
func reasonText(_ r: ReasonCode) -> String {
    let i = Prefs.shared.resolved.index
    guard var s = Strings.reasons[r.k]?[i] else { return r.k }
    for (k, v) in r.p { s = s.replacingOccurrences(of: "{\(k)}", with: v) }
    return s
}

/// 标签（core 写的是中文）→ 当前语言
func tagText(_ t: String) -> String {
    let i = Prefs.shared.resolved.index
    if let v = Strings.tags[t] { return v[i] }
    if t.hasPrefix("字幕:") { return (Strings.tags["字幕"]?[i] ?? "Subs") + ":" + t.dropFirst(3) }
    return t
}

/// 校验项名（core 的 checks 键）→ 当前语言
func checkName(_ k: String) -> String { Strings.checks[k]?[Prefs.shared.resolved.index] ?? k }

// MARK: - 格式化

enum Fmt {
    static func bytes(_ b: Int64) -> String {
        let d = Double(b)
        if d >= 1_073_741_824 { return String(format: "%.2f GB", d / 1_073_741_824) }
        if d >= 1_048_576 { return String(format: d >= 100 * 1_048_576 ? "%.0f MB" : "%.1f MB", d / 1_048_576) }
        return String(format: "%.0f KB", d / 1024)
    }

    static func duration(_ s: Double) -> String {
        if s < 60 { return T("time.lt1m") }
        let m = Int((s / 60).rounded())
        if m < 60 { return T("time.m", m) }
        return T("time.hm", m / 60, m % 60)
    }

    static func percent(_ r: Double?) -> String {
        guard let r else { return "—" }
        return String(format: "%.0f%%", r * 100)
    }

    static func value(_ v: Double) -> String { T("value.unit", v >= 100 ? String(format: "%.0f", v) : String(format: "%.1f", v)) }
}
