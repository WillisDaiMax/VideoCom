import AppKit
import SwiftUI

struct WaitView: View {
    @EnvironmentObject var model: AppModel
    @State private var confirmUndo = false

    private var m: Manifest? { model.manifest }
    private func n(_ key: String) -> Int { (model.status[key] as? NSNumber)?.intValue ?? 0 }
    private func entries(_ b: Bucket) -> [Entry] { m?.entries.filter { $0.bucket == b.rawValue } ?? [] }

    var body: some View {
        let waiting = (m?.entries ?? []).filter { $0.bucket == "compress" && ["moved", "unmatched", "writing"].contains($0.state) }
        let left = model.totals(waiting)
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                PageHeader(title: T("wait.title"), subtitle: T("wait.subtitle"))

                HStack(spacing: 10) {
                    StatCard(title: T("wait.pending"), value: "\(n("pending"))", icon: "hourglass", color: Palette.text2)
                    StatCard(title: T("wait.ready"), value: "\(n("ready"))", icon: "checkmark.circle", color: Palette.accent)
                    StatCard(title: T("wait.writing"), value: "\(n("writing"))", icon: "arrow.down.doc", color: Palette.warn)
                    StatCard(title: T("wait.left"), value: left.count > 0 ? Fmt.duration(left.seconds) : "—",
                             icon: "clock", color: Palette.text,
                             sub: left.count > 0 ? T("wait.leftSub", Fmt.bytes(left.src), Fmt.bytes(left.out)) : nil)
                }

                if let m {
                    let comp = entries(.compress)
                    if !comp.isEmpty, let engine = m.engine["compress"] {
                        let app = engine.replacingOccurrences(of: "external:", with: "")
                        TaskCard(icon: Bucket.compress.icon, color: Palette.accent,
                                 title: T("wait.compressCard", app, comp.count),
                                 lines: instructions(line: m.line, comp: comp)) {
                            Button(T("wait.openCompress")) { NSWorkspace.shared.open(URL(fileURLWithPath: m.dirs["compress"] ?? "")) }
                            Button(T("wait.openOutput")) { NSWorkspace.shared.open(URL(fileURLWithPath: m.dirs["output"] ?? "")) }
                            if let url = model.appURL(for: engine) {
                                Button(T("wait.openApp", url.deletingPathExtension().lastPathComponent)) { NSWorkspace.shared.open(url) }
                            }
                        }
                    }
                    let rem = entries(.remux)
                    if !rem.isEmpty {
                        TaskCard(icon: Bucket.remux.icon, color: Bucket.remux.color, title: T("wait.remuxCard", rem.count),
                                 lines: [T("wait.remuxLine")]) { EmptyView() }
                    }
                    let rev = entries(.review)
                    if !rev.isEmpty {
                        TaskCard(icon: Bucket.review.icon, color: Palette.warn, title: T("wait.reviewCard", rev.count),
                                 lines: [T("wait.reviewLine")]) {
                            Button(T("wait.openFolder")) { NSWorkspace.shared.open(URL(fileURLWithPath: m.dirs["review"] ?? "")) }
                        }
                    }
                }

                HStack(spacing: 10) {
                    Button { Task { await model.finish() } } label: {
                        Label(T("wait.finish"), systemImage: "wand.and.stars")
                    }
                    .buttonStyle(.primary)
                    .help(T("wait.finishHelp"))
                    Button { Task { await model.refreshStatus() } } label: { Label(T("wait.refresh"), systemImage: "arrow.clockwise") }
                        .buttonStyle(.secondary)
                    Spacer()
                    Button { confirmUndo = true } label: { Label(T("wait.undo"), systemImage: "arrow.uturn.backward") }
                        .buttonStyle(.secondary)
                }
                Text(T("wait.autoRefresh")).font(Typo.caption).foregroundStyle(Palette.text3)
            }
            .padding(32)
            .frame(maxWidth: 900, alignment: .leading)
        }
        .task { await model.refreshStatus() }
        .confirmationDialog(T("wait.undo.title"), isPresented: $confirmUndo) {
            Button(T("wait.undo"), role: .destructive) { Task { await model.undo() } }
            Button(T("common.cancel"), role: .cancel) {}
        } message: {
            Text(T("wait.undo.message"))
        }
    }

    private func instructions(line: String, comp: [Entry]) -> [String] {
        let out = URL(fileURLWithPath: m?.dirs["output"] ?? "").lastPathComponent
        if line == "daily" {
            var l = [T("wait.daily.1", out)]
            let hdr = comp.filter { $0.tags.contains { t in t.hasPrefix("HLG") || t.hasPrefix("HDR") || t.hasPrefix("Dolby") } }.count
            if hdr > 0 { l.append(T("wait.daily.hdr", hdr)) }
            l.append(T("wait.daily.2"))
            return l
        }
        return [T("wait.movie.1", out), T("wait.movie.2")]
    }
}

struct TaskCard<Actions: View>: View {
    let icon: String
    let color: Color
    let title: String
    let lines: [String]
    @ViewBuilder let actions: () -> Actions

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: icon).font(.system(size: 12, weight: .semibold))
                    .frame(width: 26, height: 26)
                    .background(color.opacity(0.14), in: RoundedRectangle(cornerRadius: 7, style: .continuous))
                    .foregroundStyle(color)
                Text(title).font(Typo.title)
            }
            VStack(alignment: .leading, spacing: 5) {
                ForEach(lines, id: \.self) { l in
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Circle().fill(Palette.text3).frame(width: 4, height: 4).offset(y: -2)
                        Text(l).font(Typo.body).foregroundStyle(Palette.text2).fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
            HStack(spacing: 8) { actions() }.buttonStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .card(padding: 18, radius: 14)
    }
}
