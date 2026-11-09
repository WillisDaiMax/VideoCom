import SwiftUI

struct ResultView: View {
    @EnvironmentObject var model: AppModel
    @State private var onlyIssues = false
    @State private var includeWarn = false
    @State private var showCleanup = false

    private var all: [Entry] { model.manifest?.entries ?? [] }
    private var shown: [Entry] {
        let base = all.filter { ["compress", "remux"].contains($0.bucket) }
        let list = onlyIssues ? base.filter { $0.isAnomaly || !$0.warnings.isEmpty } : base
        return list.sorted { ($0.isAnomaly ? 0 : 1, $0.id) < ($1.isAnomaly ? 0 : 1, $1.id) }
    }
    private var done: [Entry] { all.filter { ($0.state == "verified" || $0.state == "trashed") && $0.out_probe != nil } }
    private var before: Int64 { done.reduce(0) { $0 + $1.size } }
    private var after: Int64 { done.reduce(0) { $0 + ($1.outSize ?? 0) } }

    var body: some View {
        VStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 16) {
                PageHeader(title: T("result.title")) {
                    Button { model.openReport() } label: { Label(T("result.openReport"), systemImage: "doc.richtext") }
                        .buttonStyle(.secondary)
                }
                HStack(spacing: 10) {
                    StatCard(title: T("result.passed"), value: "\(done.count)", icon: "checkmark.seal", color: Palette.accent)
                    StatCard(title: T("result.saved"), value: Fmt.bytes(max(0, before - after)), icon: "arrow.down.circle",
                             color: Palette.text, sub: "\(Fmt.bytes(before)) → \(Fmt.bytes(after))")
                    StatCard(title: T("result.ratio"), value: Fmt.percent(before > 0 ? Double(after) / Double(before) : nil),
                             icon: "percent", color: Palette.text)
                    StatCard(title: T("result.anomalies"), value: "\(all.filter(\.isAnomaly).count)", icon: "exclamationmark.triangle",
                             color: all.contains(where: \.isAnomaly) ? Palette.danger : Palette.text2)
                    StatCard(title: T("result.trashed"), value: "\(all.filter { $0.state == "trashed" }.count)", icon: "trash",
                             color: Palette.text2)
                }
                HStack {
                    Toggle(T("result.onlyIssues"), isOn: $onlyIssues).toggleStyle(.switch).controlSize(.small)
                        .font(Typo.body)
                    Spacer()
                }
            }
            .padding(.horizontal, 28).padding(.top, 28).padding(.bottom, 12)

            HStack(spacing: 12) {
                Text(T("col.file")).frame(maxWidth: .infinity, alignment: .leading)
                Text(T("col.state")).frame(width: 96, alignment: .leading)
                Text(T("col.size")).frame(width: 74, alignment: .trailing)
                Text(T("col.newSize")).frame(width: 74, alignment: .trailing)
                Text(T("col.ratioActual")).frame(width: 110, alignment: .leading)
            }
            .font(Typo.captionMedium).foregroundStyle(Palette.text3)
            .padding(.horizontal, 28).padding(.vertical, 8)
            Divider().overlay(Palette.stroke)

            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(shown) { e in
                        ResultRow(entry: e)
                        Divider().overlay(Palette.stroke).padding(.leading, 28)
                    }
                }
            }

            HStack(spacing: 10) {
                Button(T("result.newBatch")) { model.newBatch() }.buttonStyle(.secondary)
                Button { Task { await model.finish() } } label: { Label(T("result.again"), systemImage: "arrow.clockwise") }
                    .buttonStyle(.secondary).help(T("result.againHelp"))
                Spacer()
                Toggle(T("result.includeWarn"), isOn: $includeWarn).controlSize(.small).font(Typo.body)
                Button {
                    Task {
                        await model.previewCleanup(includeWarn: includeWarn)
                        showCleanup = model.cleanupPreview != nil
                    }
                } label: {
                    Label(T("result.cleanup"), systemImage: "trash")
                }
                .buttonStyle(.danger)
            }
            .padding(.horizontal, 28).padding(.vertical, 14)
            .overlay(alignment: .top) { Divider().overlay(Palette.stroke) }
        }
        .confirmationDialog(cleanupTitle, isPresented: $showCleanup) {
            if let p = model.cleanupPreview, !p.ids.isEmpty {
                Button(T("result.cleanup.button"), role: .destructive) { Task { await model.cleanup(includeWarn: includeWarn) } }
            }
            Button(T("common.cancel"), role: .cancel) { model.cleanupPreview = nil }
        } message: {
            Text(T("result.cleanup.message"))
        }
    }

    private var cleanupTitle: String {
        guard let p = model.cleanupPreview else { return "" }
        if p.ids.isEmpty { return T("result.cleanup.none") }
        return T("result.cleanup.title", p.ids.count, Fmt.bytes(p.freed))
    }
}

private struct ResultRow: View {
    @EnvironmentObject var model: AppModel
    let entry: Entry
    @State private var hover = false

    var body: some View {
        let e = entry
        let color: Color = e.isAnomaly ? Palette.danger : (e.state == "verified" ? (e.warnings.isEmpty ? Palette.accent : Palette.warn) : Palette.text2)
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(e.name).font(Typo.bodyMedium).lineLimit(1).truncationMode(.middle)
                ForEach(e.failures, id: \.0) { k, v in
                    Text("\(checkName(k)): \(v)").font(Typo.caption).foregroundStyle(Palette.danger).lineLimit(2)
                }
                ForEach(e.warnings, id: \.0) { k, v in
                    Text("\(checkName(k)): \(v)").font(Typo.caption).foregroundStyle(Palette.warn).lineLimit(2)
                }
                if e.state == "unmatched" {
                    Text(T("result.unmatched")).font(Typo.caption).foregroundStyle(Palette.danger)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Pill(text: T("state.\(e.state)"), color: color).frame(width: 96, alignment: .leading)
            Text(Fmt.bytes(e.size)).font(Typo.mono).foregroundStyle(Palette.text2).frame(width: 74, alignment: .trailing)
            Text(e.outSize.map(Fmt.bytes) ?? "—").font(Typo.mono).frame(width: 74, alignment: .trailing)
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text(Fmt.percent(e.actualRatio)).font(Typo.mono)
                    if let est = e.estimate?.ratio, e.actualRatio != nil {
                        Text(T("result.est", Fmt.percent(est))).font(Typo.caption).foregroundStyle(Palette.text3)
                    }
                }
                if let r = e.actualRatio { Bar(value: r, color: color.opacity(0.8)).frame(width: 90) }
            }
            .frame(width: 110, alignment: .leading)
        }
        .padding(.horizontal, 28).padding(.vertical, 10)
        .background(hover ? Palette.cardHi.opacity(0.45) : Color.clear)
        .contentShape(Rectangle())
        .onHover { hover = $0 }
        .contextMenu {
            Button(T("result.revealSrc")) { model.reveal(e.src_now) }
            if let o = e.output { Button(T("result.revealOut")) { model.reveal(o) } }
        }
    }
}
