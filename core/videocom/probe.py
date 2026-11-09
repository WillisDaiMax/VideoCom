"""
probe.py — 读取视频信息（只读）。

summarize() 把 ffprobe 结果压成一份"轨道清单 + 编码参数"，分类、匹配、对比报告都用它。
"""
import json
import subprocess
from fractions import Fraction
from pathlib import Path

from . import config

IMAGE_SUBS = {"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "xsub"}
TEXT_SUBS = {"subrip", "ass", "ssa", "mov_text", "webvtt", "text"}
QT_EXT = {".mov", ".mp4", ".m4v", ".3gp"}


def run(cmd, timeout=180):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _fps(s):
    try:
        v = float(Fraction(s))
        return v if v > 0 else None
    except Exception:
        return None


def _lang(st):
    return ((st.get("tags") or {}).get("language") or "und").lower()


def ffprobe(cfg, path):
    exe = config.tool(cfg, "ffprobe")
    if not exe:
        raise RuntimeError("找不到 ffprobe")
    r = run([exe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
             "-show_chapters", str(path)])
    if r.returncode != 0:
        raise RuntimeError((r.stderr.strip() or "ffprobe 失败")[:300])
    return json.loads(r.stdout)


def _video_bitrate(v, fmt, streams):
    """返回 (码率, 是否估算)。"""
    if v.get("bit_rate"):
        return int(v["bit_rate"]), False
    tags = {k.upper(): str(val) for k, val in (v.get("tags") or {}).items()}
    for k in ("BPS", "BPS-ENG"):
        if tags.get(k, "").isdigit():
            return int(tags[k]), False
    total = int(fmt.get("bit_rate") or 0)
    if not total:
        return None, True
    audio = sum(int(s.get("bit_rate") or 0) for s in streams if s.get("codec_type") == "audio")
    return max(total - audio, int(total * 0.6)), True


def summarize(cfg, path):
    """返回 dict；读不了时抛异常。"""
    path = Path(path)
    info = ffprobe(cfg, path)
    fmt, streams = info.get("format", {}), info.get("streams", [])
    vids = [s for s in streams if s.get("codec_type") == "video"
            and not (s.get("disposition") or {}).get("attached_pic")]
    auds = [s for s in streams if s.get("codec_type") == "audio"]
    subs = [s for s in streams if s.get("codec_type") == "subtitle"]
    datas = [s for s in streams if s.get("codec_type") == "data"]
    atts = [s for s in streams if s.get("codec_type") == "attachment"]
    dur = float(fmt.get("duration") or 0)
    s = {
        "container": fmt.get("format_name", ""),
        "duration": round(dur, 3),
        "size": path.stat().st_size,
        "audio": [{"codec": a.get("codec_name"), "lang": _lang(a), "ch": a.get("channels")} for a in auds],
        "subs": [{"codec": x.get("codec_name"), "lang": _lang(x),
                  "forced": bool((x.get("disposition") or {}).get("forced"))} for x in subs],
        "attachments": [((a.get("tags") or {}).get("mimetype") or "?") for a in atts],
        "chapters": len(info.get("chapters", [])),
        "data": [((d.get("tags") or {}).get("handler_name") or d.get("codec_tag_string") or "?") for d in datas],
        "video_tracks": len(vids),
    }
    if not vids:
        s["codec"] = None
        return s
    v = vids[0]
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    f = _fps(v.get("avg_frame_rate", "0/0")) or _fps(v.get("r_frame_rate", "0/0")) or 30.0
    fr = _fps(v.get("r_frame_rate", "0/0"))
    br, est = _video_bitrate(v, fmt, streams)
    pix = v.get("pix_fmt", "") or ""
    side = v.get("side_data_list", []) or []
    dv = None
    for d in side:
        if "DOVI" in (d.get("side_data_type") or "").upper() or "Dolby Vision" in (d.get("side_data_type") or ""):
            dv = d.get("dv_profile", "?")
    if dv is None and v.get("codec_tag_string") in ("dvh1", "dvhe"):
        dv = "?"
    rotation = 0
    for d in side:
        if "rotation" in d:
            rotation = int(d.get("rotation") or 0)
    s.update({
        "codec": v.get("codec_name"),
        "width": w, "height": h, "fps": round(f, 3),
        "vfr": bool(fr and abs(f - fr) / fr > 0.02),
        "vbitrate": br, "vbitrate_estimated": est,
        "bpp": round(br / (w * h * f), 4) if br and w and h else None,
        "bit_depth": 10 if ("10" in pix or "12" in pix) else 8,
        "pix_fmt": pix,
        "transfer": v.get("color_transfer", "") or "",
        "hdr": {"smpte2084": "HDR10", "arib-std-b67": "HLG"}.get(v.get("color_transfer", ""), ""),
        "dv_profile": dv,
        "rotation": rotation,
    })
    return s


def exif_meta(cfg, path):
    """QuickTime 系容器的 GPS / 拍摄时间 / 相机。没有 exiftool 或非 QT 容器返回 {}。"""
    exe = config.tool(cfg, "exiftool")
    if not exe or Path(path).suffix.lower() not in QT_EXT:
        return {}
    r = run([exe, "-j", "-n", "-api", "QuickTimeUTC=1", "-api", "LargeFileSupport=1",
             "-Make", "-Model", "-GPSLatitude", "-GPSLongitude", "-CreationDate", "-CreateDate", str(path)])
    try:
        m = json.loads(r.stdout)[0]
    except Exception:
        return {}
    m.pop("SourceFile", None)
    return m
