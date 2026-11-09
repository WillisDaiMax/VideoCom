import SwiftUI

struct ReviewView: View {
    @EnvironmentObject var model: AppModel
    @State private var filter: Bucket?
    @State private var selection = Set<Int>()
    @State private var sortKey: SortKey = .value
    @State private var confirmMove = false

    private var all: [Entry] { model.manifest?.entries ?? [] }
    private var entries: [Entry] {
        let list = filter.map { f in all.filter { $0.bucket == f.rawValue } } ?? all
        return model.sorted(list, by: sortKey)
    }
    private var maxValue: Double { all.compactMap { $0.shownEstimate?.value }.max() ?? 1 }
    private func count(_ b: Bucket) -> Int { all.filter { $0.bucket == b.rawValue }.count }
    private func size(_ b: Bucket) -> Int64 { all.filter { $0.bucket == b.rawValue }.reduce(0) { $0 + $1.size } }

    var body: some View {
        let t = model.totals()
        VStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 16) {
                PageHeader(title: T("review.title"),
                           subtitle: t.count == 0 ? T("review.subtitle.none")
                               : T("review.subtitle", Fmt.bytes(t.src), Fmt.bytes(t.out),
                                   Fmt.bytes(max(0, t.src - t.out)), Fmt.percent(t.src > 0 ? Double(t.out) / Double(t.src) : nil),
                                   Fmt.duration(t.seconds)))

                HStack(spacing: 10) {
                    ForEach(Bucket.allCases) { b in
                        BucketCard(bucket: b, count: count(b), size: size(b), selected: filter == b) {
                            filter = (filter == b ? nil : b)
                        }
                    }
                }

                HStack(spacing: 10) {
                    Menu {
                        Picker("", selection: $sortKey) {
                            ForEach(SortKey.allCases) { Text($0.title).tag($0) }
                        }
                        .pickerStyle(.inline).labelsHidden()
                    } label: {
                        Label(T("review.sort", sortKey.title), systemImage: "arrow.up.arrow.down")
                            .font(Typo.bodyMedium)
                    }
                    .menuStyle(.borderlessButton).fixedSize()

                    if !selection.isEmpty {
                        Divider().frame(height: 14)
                        Text(T("review.selected", selection.count)).font(Typo.body).foregroundStyle(Palette.text2)
                        Menu(T("review.batchChange")) {
                            ForEach(Bucket.allCases) { b in
                                Button(b.title) { Task { await model.setBucket(ids: Array(selection), bucket: b); selection = [] } }
                            }
                        }
                        .menuStyle(.borderlessButton).fixedSize()
                        Button(T("review.clearSelection")) { selection = [] }.buttonStyle(.plain)
                            .font(Typo.body).foregroundStyle(Palette.text2)
                    }
                    Spacer()
                    Text(T("review.hint")).font(Typo.caption).foregroundStyle(Palette.text3)
                }
            }
            .padding(.horizontal, 28).padding(.top, 28).padding(.bottom, 12)

            ReviewHeaderRow()
            Divider().overlay(Palette.stroke)
            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(entries) { e in
                        ReviewRow(entry: e, maxValue: maxValue, selected: selection.contains(e.id)) {
                            if selection.contains(e.id) { selection.remove(e.id) } else { selection.insert(e.id) }
                        }
                        Divider().overlay(Palette.stroke).padding(.leading, 52)
                    }
                }
            }

            HStack {
                Text(T("review.estimateNote")).font(Typo.caption).foregroundStyle(Palette.text3)
                Spacer()
                Button {
                    confirmMove = true
                } label: {
                    Label(T("review.apply"), systemImage: "arrow.right")
                }
                .buttonStyle(.primary)
            }
            .padding(.horizontal, 28).padding(.vertical, 14)
            .background(Palette.panel)
            .overlay(alignment: .top) { Divider().overlay(Palette.stroke) }
        }
        .confirmationDialog(T("review.confirm.title"), isPresented: $confirmMove) {
            Button(T("review.confirm.button", all.count)) { Task { await model.apply() } }
            Button(T("common.cancel"), role: .cancel) {}
        } message: {
            Text(Bucket.allCases.map { "\($0.title) \(count($0))" }.joined(separator: " · ") + "\n" + T("review.confirm.message"))
        }
    }
}

private struct BucketCard: View {
    let bucket: Bucket
    let count: Int
    let size: Int64
    let selected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 6) {
                    Image(systemName: bucket.icon).font(.system(size: 11, weight: .semibold))
                    Text(bucket.title).font(Typo.captionMedium)
                }
                .foregroundStyle(bucket.color)
                Text("\(count)").font(Typo.number)
                Text(Fmt.bytes(size)).font(Typo.caption).foregroundStyle(Palette.text2)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(14)
            .background(Palette.card, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(selected ? bucket.color : Palette.stroke, lineWidth: selected ? 1.5 : 1))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

// 列宽
private enum Col {
    static let check: CGFloat = 24
    static let bucket: CGFloat = 112
    static let size: CGFloat = 74
    static let est: CGFloat = 74
    static let ratio: CGFloat = 84
    static let time: CGFloat = 70
    static let value: CGFloat = 96
}

private struct ReviewHeaderRow: View {
    var body: some View {
        HStack(spacing: 12) {
            Color.clear.frame(width: Col.check)
            Text(T("col.file")).frame(maxWidth: .infinity, alignment: .leading)
            Text(T("col.bucket")).frame(width: Col.bucket, alignment: .leading)
            Text(T("col.size")).frame(width: Col.size, alignment: .trailing)
            Text(T("col.estSize")).frame(width: Col.est, alignment: .trailing)
            Text(T("col.ratio")).frame(width: Col.ratio, alignment: .leading)
            Text(T("col.time")).frame(width: Col.time, alignment: .trailing)
            Text(T("col.value")).frame(width: Col.value, alignment: .leading)
        }
        .font(Typo.captionMedium)
        .foregroundStyle(Palette.text3)
        .padding(.horizontal, 28).padding(.vertical, 8)
    }
}

private struct ReviewRow: View {
    @EnvironmentObject var model: AppModel
    let entry: Entry
    let maxValue: Double
    let selected: Bool
    let toggle: () -> Void
    @State private var hover = false

    var body: some View {
        let e = entry
        let b = Bucket(rawValue: e.bucket) ?? .review
        let est = e.shownEstimate
        HStack(spacing: 12) {
            Button(action: toggle) {
                Image(systemName: selected ? "checkmark.square.fill" : "square")
                    .font(.system(size: 14))
                    .foregroundStyle(selected ? Palette.accent : Palette.text3)
            }
            .buttonStyle(.plain).frame(width: Col.check)

            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text(e.name).font(Typo.bodyMedium).lineLimit(1).truncationMode(.middle)
                    Text([e.probe?.codec, e.probe?.resolution].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "))
                        .font(Typo.caption).foregroundStyle(Palette.text3).lineLimit(1)
                }
                Text(reasons(e)).font(Typo.caption).foregroundStyle(Palette.text2).lineLimit(1)
                    .help(reasons(e, sep: "\n"))
                if !e.tags.isEmpty {
                    Text(e.tags.map(tagText).joined(separator: " · ")).font(Typo.caption).foregroundStyle(Palette.text3).lineLimit(1)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            Menu {
                ForEach(Bucket.allCases) { nb in
                    Button(nb.title) { Task { await model.setBucket(ids: [e.id], bucket: nb) } }
                }
            } label: {
                Pill(text: b.title, color: b.color)
            }
            .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
            .frame(width: Col.bucket, alignment: .leading)

            Text(Fmt.bytes(e.size)).font(Typo.mono).foregroundStyle(Palette.text2)
                .frame(width: Col.size, alignment: .trailing)
            Text(est.map { Fmt.bytes($0.out_size) } ?? "—").font(Typo.mono)
                .frame(width: Col.est, alignment: .trailing)
            HStack(spacing: 6) {
                if let r = est?.ratio {
                    Bar(value: r, color: Palette.accent.opacity(0.75)).frame(width: 38)
                    Text(Fmt.percent(r)).font(Typo.mono)
                } else {
                    Text("—").font(Typo.mono).foregroundStyle(Palette.text3)
                }
            }
            .frame(width: Col.ratio, alignment: .leading)
            Text(est.map { Fmt.duration($0.seconds) } ?? "—").font(Typo.mono).foregroundStyle(Palette.text2)
                .frame(width: Col.time, alignment: .trailing)
            VStack(alignment: .leading, spacing: 3) {
                if let v = est?.value, e.bucket == "compress" {
                    Text(Fmt.value(v)).font(Typo.mono)
                    Bar(value: maxValue > 0 ? v / maxValue : 0, color: Palette.accent)
                } else {
                    Text("—").font(Typo.mono).foregroundStyle(Palette.text3)
                }
            }
            .frame(width: Col.value, alignment: .leading)
        }
        .padding(.horizontal, 28).padding(.vertical, 9)
        .background(selected ? Palette.accentSoft : (hover ? Palette.cardHi.opacity(0.45) : Color.clear))
        .contentShape(Rectangle())
        .onHover { hover = $0 }
        .onTapGesture(count: 2) { model.reveal(e.src_now) }
        .contextMenu {
            ForEach(Bucket.allCases) { nb in
                Button(T("review.changeTo", nb.title)) { Task { await model.setBucket(ids: [e.id], bucket: nb) } }
            }
            Divider()
            Button(T("common.reveal")) { model.reveal(e.src_now) }
        }
    }

    private func reasons(_ e: Entry, sep: String = " · ") -> String {
        if let rc = e.reason_codes, !rc.isEmpty { return rc.map(reasonText).joined(separator: sep) }
        return e.reasons.joined(separator: sep)
    }
}
