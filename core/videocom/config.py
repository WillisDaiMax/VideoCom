"""
config.py — 默认规则、目录名、外部工具路径。

用户覆盖：~/Library/Application Support/VideoCom/config.json（只写想改的键，深合并到默认值上）。
改阈值、后缀、子目录名都在这里，不需要动逻辑代码。
"""
import json
import os
import shutil
from pathlib import Path

RULES_VERSION = 1
MANIFEST_NAME = "videocom.json"
MANIFEST_VERSION = 1

LINES = ("daily", "movie")
LINE_LABEL = {"daily": "一般视频（MP4）", "movie": "电影（MKV）"}

# 桶：每个文件在分类后进入其中一个
BUCKETS = ("compress", "skip", "review", "remux")
BUCKET_LABEL = {"compress": "要压缩", "skip": "不用压缩", "review": "需人工确认", "remux": "仅转封装"}

DEFAULTS = {
    "scan_ext": [".mov", ".mp4", ".m4v", ".mkv", ".ts", ".mts", ".m2ts", ".avi", ".wmv",
                 ".webm", ".mpg", ".mpeg", ".flv", ".3gp", ".vob", ".rmvb", ".rm"],
    "exclude_dirs": [".Trashes", ".Spotlight-V100", ".fseventsd", ".DocumentRevisions-V100", "@eaDir"],
    "legacy_codecs": ["h264", "mpeg2video", "mpeg1video", "mpeg4", "msmpeg4v2", "msmpeg4v3", "vc1",
                      "wmv1", "wmv2", "wmv3", "mjpeg", "flv1", "h263", "theora", "vp8", "rv30", "rv40"],
    "efficient_codecs": ["hevc", "av1", "vp9"],
    "master_codecs": ["prores", "dnxhd", "ffv1", "rawvideo", "cineform", "huffyuv", "utvideo"],
    # bpp = 视频码率 / (宽 × 高 × 帧率)
    "bpp_low": 0.035,                                   # 低于此值的旧编码：收益有限 → 不用压缩
    "bpp_efficient_high": {"daily": 0.09, "movie": 0.07},  # 高于此值的 HEVC/AV1/VP9：仍值得压缩
    "min_size_mb": 0,                                   # 小于此体积 → 不用压缩；0 = 不考虑原视频大小
    "target_container": {"daily": "mp4", "movie": "mkv"},
    # 一般视频要压缩的文件按 HDR/SDR 分子文件夹（2026-11-09 起默认关闭：待压缩只要一层）
    "daily_split_hdr": False,
    # 一般视频线：有空间音频（iPhone 16 起默认录制的 APAC 轨）时是否进"需人工确认"。
    # False = 照常压缩，只保留立体声 AAC，空间音频轨会丢
    "daily_review": {"spatial_audio": True},
    # 电影线哪些情况进"需人工确认"
    "movie_review": {"dv_profile7": True, "ass_with_fonts": True},
    # 预估（estimate.py）。cap_bpp / factor / px_per_s 按 2026-11-09 实测标定，之后由 history.json 自动修正
    "estimate": {
        "daily": {"cap_bpp": 0.03, "px_per_s": 8.5e8,
                  "factor": {"default": 0.55, "hevc": 0.8, "av1": 0.95, "vp9": 0.85,
                             "mpeg2video": 0.45, "mpeg4": 0.5, "msmpeg4v3": 0.5, "wmv3": 0.5}},
        "movie": {"cap_bpp": 0.03, "px_per_s": 8.5e8,
                  "factor": {"default": 0.55, "hevc": 0.8, "av1": 0.95, "vp9": 0.85,
                             "mpeg2video": 0.45, "mpeg4": 0.5, "rv40": 0.55, "rv30": 0.55, "wmv3": 0.5}},
        "copy_mb_per_s": 300,
    },
    # 匹配
    "output_suffixes": ["_converted", "_hevc", "_h265", "_x265", "_compressed", "_opt", "_c1", "_c2",
                        "_c3", "_c4", "_c5", "_c6", "_c7", "_c8", "_c9", "_c10", "_remux", "-converted", " converted"],
    "duration_tolerance_s": 0.5,
    "duration_tolerance_pct": 0.2,      # 长片按比例放宽：max(0.5s, 0.2%)
    "stable_seconds": 30,               # 输出文件多久没变化视为写完
    # 批次子目录名（可在 scan 时用 --dir-<桶> 改成任意绝对路径）
    "dirs": {
        "compress": "1_待压缩",
        "skip": "2_无需压缩",
        "review": "3_需人工确认",
        "remux": "4_仅转封装",
        "output": "5_输出",
        "report": "6_报告",
    },
    "tools": {"ffprobe": "", "ffmpeg": "", "exiftool": "", "setfile": ""},
}

USER_CONFIG = Path.home() / "Library" / "Application Support" / "VideoCom" / "config.json"
SEARCH_PATHS = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]


def _merge(base, over):
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def load(path=None):
    cfg = DEFAULTS
    p = Path(path) if path else Path(os.environ.get("VIDEOCOM_CONFIG", USER_CONFIG))
    if p.is_file():
        cfg = _merge(DEFAULTS, json.loads(p.read_text(encoding="utf-8")))
    return cfg


def tool(cfg, name):
    """找外部工具：config 指定 > PATH > Homebrew 常见位置。找不到返回 None。"""
    exe = {"setfile": "SetFile"}.get(name, name)
    given = (cfg.get("tools") or {}).get(name)
    if given and Path(given).exists():
        return given
    found = shutil.which(exe)
    if found:
        return found
    for d in SEARCH_PATHS:
        p = Path(d) / exe
        if p.exists():
            return str(p)
    return None
