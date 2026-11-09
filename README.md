<p align="center"><img src="app/Resources/AppIcon.png" width="128" alt="VideoCom icon"></p>

<h1 align="center">VideoCom</h1>

<p align="center">Sort, transcode-handoff and verify your video library on macOS — without losing GPS, capture dates or subtitles.<br>
整理、交给转码器、再校验你的视频 —— 不丢 GPS、拍摄时间和字幕。</p>

<p align="center"><a href="../../releases/latest">Download the latest .dmg</a> · English · <a href="#中文">中文</a></p>

---

## What it does

VideoCom handles everything **around** transcoding. The encoding itself is done by apps that already do it well:

| Line | Output | Transcoder | VideoCom adds |
|---|---|---|---|
| Everyday videos (iPhone, downloads) | MP4 / HEVC | Aagedal Media Converter | Restores GPS, capture date and file dates so the iPhone Photos app recognises them |
| Movies | MKV / HEVC | [HandBrake](https://handbrake.fr) | Checks every audio / subtitle / attachment / chapter track survived |

1. **Scan** a folder (read-only) and sort each file into *Compress / Skip / Review / Remux only*
2. See the **estimated output size, time, compression ratio and value (MB saved per minute)** for every file, sorted by what's most worth compressing
3. **Confirm** — files are moved into a batch folder (undo anytime)
4. Transcode in Aagedal / HandBrake; VideoCom can be closed meanwhile
5. **Finish** — outputs are matched by name, then double-checked by duration and resolution
6. Everyday videos: Apple metadata is written back to `moov/meta` (where Photos reads it), then file system dates
7. **Report** (HTML + CSV), problems first
8. Optional **clean-up**: originals that passed and got smaller go to the Trash, only after you confirm

Estimates start from measured defaults and **self-calibrate** from every finished batch.

## Install

1. Download `VideoCom-x.y.z.dmg` from [Releases](../../releases/latest) and drag VideoCom to Applications.
2. The app is not notarized. On first launch, right-click → Open, or run:
   ```bash
   xattr -dr com.apple.quarantine /Applications/VideoCom.app
   ```
3. Install the tools it calls:
   ```bash
   xcode-select --install          # python3, SetFile
   brew install ffmpeg exiftool
   ```

Requires macOS 14+ on Apple silicon. Languages: English, 简体中文, 繁體中文（台灣）, 日本語. Light / dark / follow system.

## Build from source

```bash
cd app
./run_dev.sh                 # run without packaging
./build_app.sh 0.2.0         # → app/build/VideoCom.app
./make_dmg.sh 0.2.0          # → app/build/VideoCom-0.2.0.dmg
```

Every tag `v*` builds the .dmg on GitHub Actions and attaches it to the release.

## Command line

The app is a SwiftUI shell over a Python core (standard library only). The core works on its own:

```bash
cd core
./vc scan --line daily --src ~/Movies/iPhone --root ~/Movies [--min-size-mb 0]
./vc show --batch ~/Movies/VideoCom-daily-…
./vc set-bucket --batch … --ids 3,7 --bucket review
./vc apply  --batch …          # move files, run built-in remux
./vc status --batch …
./vc finish --batch …          # match → restore metadata → verify → report
./vc cleanup --batch …         # lists only; add --yes to move to Trash
./vc undo --batch …
```

Add `--events` for JSON-lines output (what the app uses).

## Configuration

Override only the keys you need in `~/Library/Application Support/VideoCom/config.json`:

```json
{"min_size_mb": 30, "daily_review": {"spatial_audio": false}, "movie_review": {"ass_with_fonts": false}}
```

All options are in [`core/videocom/config.py`](core/videocom/config.py). Calibration history lives next to it in `history.json`.

## Why iPhone Photos sometimes ignores the date and location

Photos reads Apple metadata (`com.apple.quicktime.creationdate`, `location.ISO6709`) **only** from `moov/meta`.
`ffmpeg -movflags +use_metadata_tags` writes it to `moov/udta/meta`: the values are there, Photos just doesn't look.
VideoCom removes that copy, writes the metadata from the original into `moov/meta`, sets the movie/track dates to the capture time,
and verifies the result in a *Readable by Photos* check.

## Transcoder engines

Each category is handled by an engine recorded in the batch (`external:Aagedal`, `external:HandBrake`, `builtin:remux`).
`builtin:encode` is reserved in [`core/videocom/engines.py`](core/videocom/engines.py) for a future built-in ffmpeg encoder.

## License

[GPL-3.0](LICENSE) — you may use, modify and redistribute VideoCom, but derivative works must also be released under GPL-3.0 with their source code.

---

## 中文

VideoCom 负责转码**前后**的工作，转码本身交给 Aagedal（一般视频 → MP4）和 HandBrake（电影 → MKV）。

**流程**：扫描（只读）→ 预览分类，显示预计大小、耗时、压缩率、性价比（每分钟能省多少 MB），并按性价比排序 → 确认后移动（可撤销）→ 外部转码 → 收尾：按文件名配对，再用时长和分辨率复核 → 一般视频把 GPS 和拍摄时间写回 `moov/meta`（iPhone「照片」只读这里），最后写文件时间 → 生成报告 → 可选：把原片移到废纸篓（需确认）。

**安装**：在 [Releases](../../releases/latest) 下载 dmg，把 VideoCom 拖进「应用程序」。App 没有经过公证，第一次打开请右键 → 打开，或运行 `xattr -dr com.apple.quarantine /Applications/VideoCom.app`。依赖：`xcode-select --install`、`brew install ffmpeg exiftool`。

**界面**：简体中文、繁體中文（台灣）、English、日本語；浅色、深色、跟随系统。

**预估**：初始参数来自实测，之后每完成一批会自动校准（记录在 `history.json`）。

**许可证**：GPL-3.0。可自由使用、修改、再发布，但基于它的衍生作品也必须以 GPL-3.0 开源并公开源代码。

**配置**：在 `~/Library/Application Support/VideoCom/config.json` 里只写要改的项，全部选项见 `core/videocom/config.py`。
