import AppKit
import SwiftUI

@main
struct VideoComApp: App {
    @StateObject private var model = AppModel()
    @StateObject private var prefs = Prefs.shared

    init() {
        // swift run 启动时让窗口出现在前台，并用自带图标
        NSApplication.shared.setActivationPolicy(.regular)
        NSApplication.shared.activate(ignoringOtherApps: true)
        if Bundle.main.bundleIdentifier == nil, let icon = Assets.appIcon {
            NSApplication.shared.applicationIconImage = icon
        }
        NSApplication.shared.appearance = Prefs.shared.appearance.nsAppearance
    }

    var body: some Scene {
        WindowGroup("VideoCom") {
            RootView()
                .environmentObject(model)
                .environmentObject(prefs)
                .id(prefs.resolved)                      // 切换语言时整体重绘
                .preferredColorScheme(prefs.appearance.scheme)
                .frame(minWidth: 1040, minHeight: 660)
        }
        .windowStyle(.hiddenTitleBar)
        .commands {
            CommandGroup(replacing: .newItem) {
                Button(T("menu.newBatch")) { model.newBatch() }.keyboardShortcut("n")
            }
        }

        Settings {
            SettingsForm()
                .environmentObject(prefs)
                .preferredColorScheme(prefs.appearance.scheme)
                .frame(width: 380)
                .padding(20)
        }
    }
}

struct RootView: View {
    @EnvironmentObject var model: AppModel

    var body: some View {
        HStack(spacing: 0) {
            Sidebar().frame(width: 236)
            ZStack {
                Group {
                    switch model.step {
                    case .start: StartView()
                    case .review: ReviewView()
                    case .waiting: WaitView()
                    case .results: ResultView()
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                if model.busy { BusyOverlay() }
            }
            .background(Palette.panel, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(Palette.stroke))
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            .padding(.vertical, 10).padding(.trailing, 10)
        }
        .background(Palette.sidebar)
        .ignoresSafeArea()
        .foregroundStyle(Palette.text)
        .tint(Palette.accent)
        .alert(T("err.title"), isPresented: Binding(get: { model.errorMessage != nil }, set: { if !$0 { model.errorMessage = nil } })) {
            Button(T("common.ok")) { model.errorMessage = nil }
        } message: {
            Text(model.errorMessage ?? "")
        }
    }
}

// MARK: - 侧边栏（参考图：Logo + 名称，分步导航，选中项浅灰底 + 细描边）

struct Sidebar: View {
    @EnvironmentObject var model: AppModel
    @State private var showSettings = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 10) {
                if let logo = Assets.logo {
                    Image(nsImage: logo).resizable().interpolation(.high).frame(width: 30, height: 30)
                } else {
                    RoundedRectangle(cornerRadius: 8).fill(Palette.iconBlue).frame(width: 30, height: 30)
                }
                Text("VideoCom").font(.system(size: 19, weight: .bold)).tracking(-0.3)
                Spacer()
            }
            .padding(.top, 46).padding(.horizontal, 20).padding(.bottom, 26)

            VStack(spacing: 4) {
                ForEach(Step.allCases) { s in
                    SidebarItem(step: s, selected: model.step == s,
                                enabled: s.rawValue <= model.maxReachableStep.rawValue) {
                        model.step = s
                    }
                }
            }
            .padding(.horizontal, 12)

            Spacer()

            if let m = model.manifest {
                VStack(alignment: .leading, spacing: 6) {
                    Text(T("sidebar.currentBatch")).font(Typo.captionMedium).foregroundStyle(Palette.text3)
                    HStack(spacing: 6) {
                        Image(systemName: Line(rawValue: m.line)?.icon ?? "film").font(.system(size: 11, weight: .semibold))
                        Text(Line(rawValue: m.line)?.title ?? m.line).font(Typo.bodyMedium)
                    }
                    Text(URL(fileURLWithPath: m.batch_dir).lastPathComponent)
                        .font(Typo.caption).foregroundStyle(Palette.text2).lineLimit(2).truncationMode(.middle)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(12)
                .background(Palette.card.opacity(0.6), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                .padding(.horizontal, 12).padding(.bottom, 10)
            }

            Button { showSettings.toggle() } label: {
                HStack(spacing: 10) {
                    Image(systemName: "gearshape").font(.system(size: 14, weight: .medium)).frame(width: 18)
                    Text(T("settings.title")).font(.system(size: 13.5, weight: .medium))
                    Spacer()
                }
                .foregroundStyle(Palette.text2)
                .padding(.horizontal, 12).padding(.vertical, 9)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 12).padding(.bottom, 16)
            .popover(isPresented: $showSettings, arrowEdge: .trailing) {
                SettingsForm().padding(18).frame(width: 320)
            }
        }
    }
}

struct SidebarItem: View {
    let step: Step
    let selected: Bool
    let enabled: Bool
    let action: () -> Void
    @State private var hover = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 11) {
                Image(systemName: step.icon)
                    .font(.system(size: 14, weight: selected ? .semibold : .regular))
                    .frame(width: 20)
                Text(step.title).font(.system(size: 13.5, weight: selected ? .semibold : .medium))
                Spacer()
            }
            .foregroundStyle(selected ? Palette.text : (enabled ? Palette.text2 : Palette.text3))
            .padding(.horizontal, 12).padding(.vertical, 10)
            .background {
                if selected {
                    RoundedRectangle(cornerRadius: 10, style: .continuous).fill(Palette.cardHi)
                        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).strokeBorder(Palette.stroke))
                        .shadow(color: .black.opacity(0.12), radius: 3, y: 1)
                } else if hover && enabled {
                    RoundedRectangle(cornerRadius: 10, style: .continuous).fill(Palette.cardHi.opacity(0.5))
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
        .onHover { hover = $0 }
    }
}

// MARK: - 设置（语言、外观）

struct SettingsForm: View {
    @EnvironmentObject var prefs: Prefs

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(T("settings.title")).font(Typo.title)
            VStack(alignment: .leading, spacing: 6) {
                Text(T("settings.language")).font(Typo.section).foregroundStyle(Palette.text2)
                Picker("", selection: $prefs.language) {
                    ForEach(Lang.allCases) { Text($0.nativeName).tag($0) }
                }
                .labelsHidden()
            }
            VStack(alignment: .leading, spacing: 6) {
                Text(T("settings.appearance")).font(Typo.section).foregroundStyle(Palette.text2)
                Picker("", selection: $prefs.appearance) {
                    Text(T("appearance.system")).tag(Appearance.system)
                    Text(T("appearance.light")).tag(Appearance.light)
                    Text(T("appearance.dark")).tag(Appearance.dark)
                }
                .labelsHidden().pickerStyle(.segmented)
            }
        }
    }
}

// MARK: - 运行中遮罩

struct BusyOverlay: View {
    @EnvironmentObject var model: AppModel

    var body: some View {
        ZStack {
            Palette.panel.opacity(0.55).ignoresSafeArea()
            VStack(spacing: 12) {
                Text(model.busyTitle).font(Typo.section)
                if let p = model.progress {
                    ProgressView(value: p).tint(Palette.accent).frame(width: 280)
                } else {
                    ProgressView().controlSize(.regular)
                }
                Text(model.progressName).font(Typo.caption).foregroundStyle(Palette.text2).lineLimit(1).frame(width: 280)
            }
            .padding(26)
            .background(Palette.card, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).strokeBorder(Palette.stroke))
            .shadow(color: .black.opacity(0.18), radius: 20, y: 8)
        }
    }
}
