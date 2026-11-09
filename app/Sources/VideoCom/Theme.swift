import AppKit
import SwiftUI

// MARK: - 颜色
// 主题蓝取自图标（顶部 #4578D9、底部 #0F2A60）；中性色：米白 / 浅灰 / 深灰 / 黑；警告：橙、橘红。

extension Color {
    init(hex: UInt32, alpha: Double = 1) {
        self.init(.sRGB,
                  red: Double((hex >> 16) & 0xFF) / 255,
                  green: Double((hex >> 8) & 0xFF) / 255,
                  blue: Double(hex & 0xFF) / 255,
                  opacity: alpha)
    }

    /// 浅色 / 深色两个值
    static func dyn(_ light: UInt32, _ dark: UInt32, alpha: Double = 1) -> Color {
        Color(nsColor: NSColor(name: nil) { ap in
            let hex = ap.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? dark : light
            return NSColor(srgbRed: CGFloat((hex >> 16) & 0xFF) / 255,
                           green: CGFloat((hex >> 8) & 0xFF) / 255,
                           blue: CGFloat(hex & 0xFF) / 255, alpha: alpha)
        })
    }
}

enum Palette {
    static let accent = Color.dyn(0x2F62C9, 0x5585E6)        // 主题蓝
    static let accentSoft = Color.dyn(0x2F62C9, 0x5585E6, alpha: 0.12)
    static let navy = Color(hex: 0x0F2A60)                    // 图标深蓝
    static let iconBlue = Color(hex: 0x4578D9)

    static let bg = Color.dyn(0xF4F1EA, 0x0E0E0D)            // 米白 / 黑
    static let sidebar = Color.dyn(0xEDE9E1, 0x161615)
    static let panel = Color.dyn(0xFAF8F4, 0x1B1B1A)         // 内容区
    static let card = Color.dyn(0xFFFFFF, 0x232322)          // 深灰卡片
    static let cardHi = Color.dyn(0xE6E2D9, 0x2D2C2A)        // 浅灰：选中 / 悬停
    static let field = Color.dyn(0xF1EEE7, 0x121211)         // 输入框
    static let stroke = Color.dyn(0x000000, 0xFFFFFF, alpha: 0.08)

    static let text = Color.dyn(0x1B1A18, 0xEDEBE7)
    static let text2 = Color.dyn(0x6E6A63, 0x9A968F)
    static let text3 = Color.dyn(0xA9A59D, 0x5C5955)

    static let warn = Color(hex: 0xF0962E)                    // 橙
    static let danger = Color(hex: 0xE5532D)                  // 橘红
    static let ok = accent

    static func bucket(_ b: Bucket) -> Color {
        switch b {
        case .compress: return accent
        case .skip: return text2
        case .review: return warn
        case .remux: return Color.dyn(0x5B74C9, 0x8EA5EE)
        }
    }
}

// MARK: - 字体（SF Pro，注意字重）

enum Typo {
    static let largeTitle = Font.system(size: 26, weight: .semibold)
    static let title = Font.system(size: 17, weight: .semibold)
    static let section = Font.system(size: 13, weight: .semibold)
    static let body = Font.system(size: 13, weight: .regular)
    static let bodyMedium = Font.system(size: 13, weight: .medium)
    static let caption = Font.system(size: 11, weight: .regular)
    static let captionMedium = Font.system(size: 11, weight: .medium)
    static let number = Font.system(size: 22, weight: .semibold).monospacedDigit()
    static let mono = Font.system(size: 12, weight: .regular).monospacedDigit()
}

// MARK: - 外观

enum Appearance: String, CaseIterable, Identifiable {
    case system, light, dark
    var id: String { rawValue }
    var scheme: ColorScheme? {
        switch self {
        case .system: return nil
        case .light: return .light
        case .dark: return .dark
        }
    }
    var nsAppearance: NSAppearance? {
        switch self {
        case .system: return nil
        case .light: return NSAppearance(named: .aqua)
        case .dark: return NSAppearance(named: .darkAqua)
        }
    }
}

// MARK: - 通用组件样式

struct Card: ViewModifier {
    var padding: CGFloat = 16
    var radius: CGFloat = 12
    func body(content: Content) -> some View {
        content
            .padding(padding)
            .background(Palette.card, in: RoundedRectangle(cornerRadius: radius, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: radius, style: .continuous).strokeBorder(Palette.stroke))
    }
}

extension View {
    func card(padding: CGFloat = 16, radius: CGFloat = 12) -> some View { modifier(Card(padding: padding, radius: radius)) }
}

struct PrimaryButtonStyle: ButtonStyle {
    var color: Color = Palette.accent
    @Environment(\.isEnabled) private var enabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .semibold))
            .foregroundStyle(.white)
            .padding(.horizontal, 16).padding(.vertical, 9)
            .background(color.opacity(enabled ? (configuration.isPressed ? 0.8 : 1) : 0.35),
                        in: RoundedRectangle(cornerRadius: 9, style: .continuous))
            .contentShape(Rectangle())
    }
}

struct SecondaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var enabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .medium))
            .foregroundStyle(enabled ? Palette.text : Palette.text3)
            .padding(.horizontal, 14).padding(.vertical, 8)
            .background(configuration.isPressed ? Palette.cardHi : Palette.card,
                        in: RoundedRectangle(cornerRadius: 9, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 9, style: .continuous).strokeBorder(Palette.stroke))
            .contentShape(Rectangle())
    }
}

extension ButtonStyle where Self == PrimaryButtonStyle {
    static var primary: PrimaryButtonStyle { PrimaryButtonStyle() }
    static var danger: PrimaryButtonStyle { PrimaryButtonStyle(color: Palette.danger) }
}

extension ButtonStyle where Self == SecondaryButtonStyle {
    static var secondary: SecondaryButtonStyle { SecondaryButtonStyle() }
}

/// 彩色小标签
struct Pill: View {
    let text: String
    let color: Color
    var body: some View {
        Text(text)
            .font(Typo.captionMedium)
            .lineLimit(1)
            .padding(.horizontal, 8).padding(.vertical, 3)
            .background(color.opacity(0.14), in: Capsule())
            .foregroundStyle(color)
    }
}

/// 统计卡片
struct StatCard: View {
    let title: String
    let value: String
    var icon: String = ""
    var color: Color = Palette.text
    var sub: String? = nil
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 5) {
                if !icon.isEmpty { Image(systemName: icon).font(.system(size: 11, weight: .semibold)) }
                Text(title).font(Typo.captionMedium)
            }
            .foregroundStyle(Palette.text2)
            Text(value).font(Typo.number).foregroundStyle(color).lineLimit(1).minimumScaleFactor(0.7)
            if let sub { Text(sub).font(Typo.caption).foregroundStyle(Palette.text3).lineLimit(1) }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .card(padding: 14)
    }
}

/// 横向比例条（压缩率、性价比）
struct Bar: View {
    let value: Double          // 0...1
    var color: Color = Palette.accent
    var body: some View {
        GeometryReader { g in
            ZStack(alignment: .leading) {
                Capsule().fill(Palette.cardHi)
                Capsule().fill(color).frame(width: max(3, g.size.width * min(1, max(0, value))))
            }
        }
        .frame(height: 5)
    }
}

/// 页头
struct PageHeader<Trailing: View>: View {
    let title: String
    var subtitle: String? = nil
    @ViewBuilder var trailing: () -> Trailing
    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title).font(Typo.largeTitle).foregroundStyle(Palette.text)
                if let subtitle { Text(subtitle).font(Typo.body).foregroundStyle(Palette.text2) }
            }
            Spacer()
            trailing()
        }
    }
}

extension PageHeader where Trailing == EmptyView {
    init(title: String, subtitle: String? = nil) {
        self.init(title: title, subtitle: subtitle) { EmptyView() }
    }
}

// MARK: - 图片资源（打包后在 .app/Contents/Resources；开发时在 app/Resources）

enum Assets {
    static func image(_ name: String) -> NSImage? {
        if let u = Bundle.main.url(forResource: name, withExtension: "png"), let i = NSImage(contentsOf: u) { return i }
        if let core = CoreRunner.coreDir {
            let p = URL(fileURLWithPath: core).deletingLastPathComponent().appendingPathComponent("app/Resources/\(name).png")
            if let i = NSImage(contentsOf: p) { return i }
        }
        return nil
    }
    static let logo = image("Logo")
    static let appIcon = image("AppIcon")
}
