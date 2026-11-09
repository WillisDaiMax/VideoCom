"""
端到端测试：用 ffmpeg 生成小视频，跑一遍 扫描 → 移动 → 模拟外部转码 → 收尾 → 清理 / 撤销。
运行：cd VideoCom/core && python3 -m unittest discover -s tests -v
需要 ffmpeg（含 libx264、libx265）；有 exiftool 时额外测 GPS/拍摄时间写回。
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from videocom import batch, config, estimate, meta, util

FF = shutil.which("ffmpeg")
ET = shutil.which("exiftool")
SRC = ["-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000"]


def ff(*args):
    subprocess.run([FF, "-v", "error", "-y", *map(str, args)], check=True)


def x265(out, src=None, br="300k", extra=()):
    inp = ["-i", src] if src else SRC
    ff(*inp, "-t", "3", "-c:v", "libx265", "-x265-params", "log-level=error", "-b:v", br, "-tag:v", "hvc1",
       "-c:a", "aac", "-shortest", *extra, out)


@unittest.skipUnless(FF, "需要 ffmpeg")
class Flow(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = config._merge(config.DEFAULTS, {"min_size_mb": 0, "stable_seconds": 0})
        util.EVENTS = True   # 安静输出
        estimate.HISTORY = self.tmp / "history.json"   # 不写本机校准记录

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_daily(self):
        src = self.tmp / "src"
        (src / "sub").mkdir(parents=True)
        ff(*SRC, "-t", "3", "-c:v", "libx264", "-b:v", "8M", "-c:a", "aac", "-shortest", src / "IMG_1.MOV")
        shutil.copy2(src / "IMG_1.MOV", src / "sub" / "IMG_1.MOV")   # 同名不同文件夹
        x265(src / "IMG_2.MOV")    # HEVC in MOV → 仅转封装
        x265(src / "IMG_3.mp4")    # HEVC in MP4 → 不用压缩
        if ET:
            subprocess.run([ET, "-q", "-overwrite_original", "-api", "QuickTimeUTC=1",
                            "-Keys:GPSCoordinates=35.6812, 139.7671",
                            "-Keys:CreationDate=2026:10:01 12:34:56+09:00", src / "IMG_1.MOV"], check=True)
        os.utime(src / "IMG_1.MOV", (1600000000, 1600000000))

        m = batch.scan(self.cfg, "daily", [src], self.tmp, name="B")
        b = {e["name"] + str(e["id"]): e["bucket"] for e in m["entries"]}
        self.assertEqual(sorted(b.values()), ["compress", "compress", "remux", "skip"])
        batch.apply(self.cfg, m)
        out = Path(m["dirs"]["output"])
        self.assertTrue((out / "IMG_2_remux.mp4").exists())
        comp = Path(m["dirs"]["compress"])
        self.assertEqual([p for p in comp.iterdir() if p.is_dir()], [])   # 待压缩只要一层
        for f in comp.glob("*.MOV"):
            # 模拟 Aagedal 自定义预设：Keys 被 ffmpeg 写进 moov/udta/meta（iPhone 照片读不到的位置）
            x265(out / f"{f.stem}_converted.mp4", src=f, br="500k",
                 extra=["-map_metadata", "0", "-movflags", "+use_metadata_tags"])
        batch.finish(self.cfg, m)
        st = {e["id"]: e["state"] for e in m["entries"]}
        self.assertEqual(sorted(st.values()), ["kept", "verified", "verified", "verified"], json.dumps(
            [e["checks"] for e in m["entries"]], ensure_ascii=False))
        e1 = next(e for e in m["entries"] if e["src_orig"].endswith("src/IMG_1.MOV"))
        self.assertTrue(e1["output"].endswith("IMG_1_converted.mp4"))      # 不会和 sub/IMG_1 的输出配错
        self.assertEqual(os.stat(e1["output"]).st_mtime, 1600000000)
        if ET:
            self.assertTrue(e1["checks"]["GPS"]["ok"] and "35.68" in e1["checks"]["GPS"]["detail"])
            self.assertTrue(e1["checks"]["照片可识别"]["ok"], e1["checks"]["照片可识别"])
            self.assertIn("com.apple.quicktime.creationdate", meta.apple_keys(e1["output"]))
        n = batch.cleanup(self.cfg, m, trash_dir=self.tmp / "trash")
        self.assertEqual(n, 3)
        self.assertTrue(Path(m["dirs"]["report"], "report.html").exists())

    def test_undo(self):
        src = self.tmp / "src"
        (src / "a").mkdir(parents=True)
        x265(src / "a" / "V.mp4")
        x265(src / "V.mp4")
        m = batch.scan(self.cfg, "daily", [src], self.tmp, name="B")
        batch.apply(self.cfg, m)
        self.assertFalse((src / "V.mp4").exists())
        batch.undo(self.cfg, m)
        self.assertTrue((src / "V.mp4").exists() and (src / "a" / "V.mp4").exists())
        self.assertEqual(m["stage"], "scanned")

    def test_movie_tracks(self):
        src = self.tmp / "src"
        src.mkdir()
        srt = self.tmp / "s.srt"
        srt.write_text("1\n00:00:00,500 --> 00:00:02,000\nHi\n")
        ff(*SRC, "-i", srt, "-i", srt, "-t", "3", "-map", "0:v", "-map", "1:a", "-map", "2", "-map", "3",
           "-c:v", "libx264", "-b:v", "8M", "-c:a", "aac", "-c:s", "srt",
           "-metadata:s:s:0", "language=chi", "-metadata:s:s:1", "language=eng", "-shortest", src / "Film.mkv")
        m = batch.scan(self.cfg, "movie", [src], self.tmp, name="M")
        self.assertEqual(m["entries"][0]["bucket"], "compress")
        batch.apply(self.cfg, m)
        f = next(Path(m["dirs"]["compress"]).rglob("*.mkv"))
        ff("-i", f, "-map", "0:v", "-map", "0:a", "-map", "0:s:0", "-c:v", "libx265", "-x265-params",
           "log-level=error", "-b:v", "500k", "-c:a", "copy", "-c:s", "copy", Path(m["dirs"]["output"]) / "Film.mkv")
        batch.finish(self.cfg, m)
        e = m["entries"][0]
        self.assertEqual(e["state"], "failed")          # 少了一条字幕 → 不通过
        self.assertFalse(e["checks"]["字幕"]["ok"])
        self.assertEqual(batch.cleanup_candidates(m), [])


if __name__ == "__main__":
    unittest.main()
