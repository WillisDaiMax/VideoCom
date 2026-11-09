import SwiftUI

struct StartView: View {
    @EnvironmentObject var model: AppModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 26) {
                PageHeader(title: T("start.title"), subtitle: T("start.subtitle")) {
                    HStack(spacing: 8) {
                        if let last = model.lastBatch, FileManager.default.fileExists(atPath: last) {
                            Button(T("start.continue")) { model.openBatch(last) }.buttonStyle(.secondary)
                        }
                        Button(T("start.openBatch")) {
                            if let u = model.pickFolders(multiple: false).first { model.openBatch(u.path) }
                        }
                        .buttonStyle(.secondary)
                    }
                }

                NumberedSection(number: 1, title: T("start.type")) {
                    HStack(spacing: 12) {
                        ForEach(Line.allCases) { l in
                            LineCard(line: l, selected: model.line == l) { model.line = l }
                        }
                    }
                }

                NumberedSection(number: 2, title: T("start.sources")) {
                    VStack(spacing: 8) {
                        if model.sources.isEmpty {
                            DropHint(text: T("start.dropHint")) { model.sources += model.pickFolders(multiple: true) }
                        } else {
                            VStack(spacing: 0) {
                                ForEach(Array(model.sources.enumerated()), id: \.element) { i, url in
                                    if i > 0 { Divider().overlay(Palette.stroke) }
                                    HStack(spacing: 10) {
                                        Image(systemName: "folder.fill").foregroundStyle(Palette.accent)
                                        Text(url.path).font(Typo.body).lineLimit(1).truncationMode(.middle)
                                        Spacer()
                                        Button { model.sources.removeAll { $0 == url } } label: {
                                            Image(systemName: "xmark").font(.system(size: 10, weight: .bold))
                                        }
                                        .buttonStyle(.plain).foregroundStyle(Palette.text3)
                                    }
                                    .padding(.vertical, 10).padding(.horizontal, 14)
                                }
                            }
                            .card(padding: 0)
                            HStack {
                                Button { model.sources += model.pickFolders(multiple: true) } label: {
                                    Label(T("start.add"), systemImage: "plus")
                                }
                                .buttonStyle(.secondary)
                                Spacer()
                            }
                        }
                    }
                    .dropDestination(for: URL.self) { urls, _ in
                        model.sources += urls.filter { !model.sources.contains($0) }
                        return true
                    }
                }

                NumberedSection(number: 3, title: T("start.root")) {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack(spacing: 10) {
                            Image(systemName: "externaldrive.fill").foregroundStyle(Palette.text2)
                            Text(model.root?.path ?? T("start.notChosen")).font(Typo.body)
                                .lineLimit(1).truncationMode(.middle)
                                .foregroundStyle(model.root == nil ? Palette.text3 : Palette.text)
                            Spacer()
                            Button(T("common.choose")) {
                                if let u = model.pickFolders(multiple: false).first { model.root = u }
                            }
                            .buttonStyle(.secondary)
                        }
                        .card(padding: 10)
                        Text(T("start.rootHint")).font(Typo.caption).foregroundStyle(Palette.text2)
                    }
                }

                NumberedSection(number: 4, title: T("start.minSize")) {
                    HStack(spacing: 8) {
                        Text(T("start.minSize.pre")).font(Typo.body)
                        TextField("0", value: $model.minSizeMB, format: .number)
                            .textFieldStyle(.plain).font(Typo.mono)
                            .multilineTextAlignment(.trailing)
                            .padding(.horizontal, 8).padding(.vertical, 5)
                            .frame(width: 72)
                            .background(Palette.field, in: RoundedRectangle(cornerRadius: 7, style: .continuous))
                            .overlay(RoundedRectangle(cornerRadius: 7, style: .continuous).strokeBorder(Palette.stroke))
                        Text(T("start.minSize.post")).font(Typo.body)
                        if model.minSizeMB <= 0 {
                            Text(T("start.minSize.zero")).font(Typo.caption).foregroundStyle(Palette.text2)
                        }
                    }
                }

                HStack {
                    Button {
                        Task { await model.scan() }
                    } label: {
                        Label(T("start.scan"), systemImage: "sparkle.magnifyingglass")
                    }
                    .buttonStyle(.primary)
                    .disabled(model.sources.isEmpty || model.root == nil)
                    Spacer()
                }
            }
            .padding(32)
            .frame(maxWidth: 860, alignment: .leading)
        }
    }
}

/// 带编号的分区
private struct NumberedSection<Content: View>: View {
    let number: Int
    let title: String
    @ViewBuilder var content: () -> Content
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Text("\(number)")
                    .font(.system(size: 11, weight: .bold)).monospacedDigit()
                    .frame(width: 20, height: 20)
                    .background(Palette.accentSoft, in: Circle())
                    .foregroundStyle(Palette.accent)
                Text(title).font(Typo.section)
            }
            content()
        }
    }
}

struct LineCard: View {
    let line: Line
    let selected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 14) {
                Image(systemName: line.icon)
                    .font(.system(size: 20, weight: .medium))
                    .frame(width: 44, height: 44)
                    .background(selected ? Palette.accent : Palette.cardHi, in: RoundedRectangle(cornerRadius: 11, style: .continuous))
                    .foregroundStyle(selected ? Color.white : Palette.text2)
                VStack(alignment: .leading, spacing: 3) {
                    Text(line.title).font(.system(size: 15, weight: .semibold))
                    Text(line.subtitle).font(Typo.caption).foregroundStyle(Palette.text2).lineLimit(2)
                }
                Spacer()
                Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 16))
                    .foregroundStyle(selected ? Palette.accent : Palette.text3)
            }
            .padding(14)
            .frame(maxWidth: .infinity)
            .background(Palette.card, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(selected ? Palette.accent : Palette.stroke, lineWidth: selected ? 1.5 : 1))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

struct DropHint: View {
    let text: String
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            VStack(spacing: 8) {
                Image(systemName: "tray.and.arrow.down").font(.system(size: 22, weight: .light))
                Text(text).font(Typo.body)
            }
            .foregroundStyle(Palette.text2)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 30)
            .background(Palette.card.opacity(0.5), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(Palette.text3, style: StrokeStyle(lineWidth: 1.2, dash: [5, 4])))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}
