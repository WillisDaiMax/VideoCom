"""
estimate.py — 预估输出大小、耗时、压缩率、性价比。

模型（每条线各一套参数，config["estimate"]）：
  输出视频 bpp = min(原 bpp × 编码系数, 上限 bpp)
  输出大小     = 输出视频码率 × 时长 + 音频（电影线直通 / 一般视频按原样估）
  耗时         = 帧数 × 像素数 ÷ 每秒处理像素
  性价比       = 预计节省 MB ÷ 预计分钟

初始参数按作者的实测标定（2026-11-09）：
  电影 VideoToolbox HEVC 10-bit CQ56：7.06 GB→1.84 GB / 7 分钟，1.44 GB→826 MB / 7 分钟，1.17 GB→687 MB / 3.5 分钟
  一般视频 Aagedal：IMG_1035 13.4 MB→2.6 MB（原 bpp 0.15 → 约 0.03）
每批收尾后，把"实际 ÷ 预估"记进 history.json；同一条线有 3 条以上记录后，用最近 20 条的中位数修正。
"""
import json
import statistics
import time
from pathlib import Path

from . import config

HISTORY = config.USER_CONFIG.parent / "history.json"
MB = 2 ** 20


def _hist():
    try:
        return json.loads(HISTORY.read_text(encoding="utf-8"))
    except Exception:
        return []


def _correction(line, key):
    xs = [h[key] for h in _hist() if h.get("line") == line and h.get(key)][-20:]
    return statistics.median(xs) if len(xs) >= 3 else 1.0, len(xs)


def raw(cfg, line, bucket, p):
    """不带历史修正的预估。p = probe 结果。"""
    size = p.get("size") or 0
    dur = p.get("duration") or 0
    if bucket == "remux":
        return {"out_size": size, "seconds": max(1.0, size / (cfg["estimate"]["copy_mb_per_s"] * MB))}
    w, h, fps = p.get("width") or 0, p.get("height") or 0, p.get("fps") or 30
    if not (dur and w and h):
        return None
    E = cfg["estimate"][line]
    codec = p.get("codec") or ""
    factor = E["factor"].get(codec, E["factor"]["default"])
    total_br = size * 8 / dur
    vbr = p.get("vbitrate") or total_br * 0.9
    abr = max(0.0, total_br - vbr)
    src_bpp = vbr / (w * h * fps)
    out_bpp = min(src_bpp * factor, E["cap_bpp"])
    out_size = (out_bpp * w * h * fps + abr) * dur / 8
    seconds = dur * fps * w * h / E["px_per_s"]
    return {"out_size": min(out_size, size), "seconds": max(1.0, seconds)}


def estimate(cfg, line, bucket, p):
    """返回 {out_size, seconds, ratio, saved, value, calibrated}；无法估计返回 None。"""
    r = raw(cfg, line, bucket, p)
    if not r:
        return None
    size = p.get("size") or 0
    if bucket != "remux":
        ks, n1 = _correction(line, "k_size")
        kt, n2 = _correction(line, "k_time")
        r["out_size"] = min(size, r["out_size"] * ks)
        r["seconds"] *= kt
        r["calibrated"] = min(n1, n2) >= 3
    saved = max(0, size - r["out_size"])
    r.update(out_size=int(r["out_size"]), seconds=round(r["seconds"], 1),
             ratio=round(r["out_size"] / size, 3) if size else None,
             saved=int(saved),
             value=round(saved / MB / max(r["seconds"] / 60, 0.05), 1))   # MB / 分钟
    return r


def attach(cfg, m, entries=None):
    """给 entries 写 estimate 字段（按当前桶；不用压缩/人工确认的也按"如果压缩"估，界面自己决定显示不显示）。"""
    for e in entries or m["entries"]:
        b = e["bucket"] if e["bucket"] in ("compress", "remux") else "compress"
        try:
            e["estimate"] = estimate(cfg, m["line"], b, e.get("probe") or {})
        except Exception:
            e["estimate"] = None


def learn(cfg, m, e):
    """收尾后记录一条"实际 ÷ 预估"。实际耗时用输出文件的创建→最后写入时间（macOS 有 Birth 时间才记）。"""
    if e["bucket"] != "compress" or not e.get("output"):
        return
    r = raw(cfg, m["line"], "compress", e.get("probe") or {})
    if not r:
        return
    out = Path(e["output"])
    rec = {"line": m["line"], "codec": (e.get("probe") or {}).get("codec"), "t": int(time.time())}
    actual = (e.get("out_probe") or {}).get("size") or out.stat().st_size
    if r["out_size"] > 0:
        rec["k_size"] = round(actual / r["out_size"], 3)
    t_actual = e.get("encode_seconds")
    if t_actual and t_actual > 5:
        rec["k_time"] = round(t_actual / r["seconds"], 3)
    h = _hist()
    h.append(rec)
    try:
        HISTORY.parent.mkdir(parents=True, exist_ok=True)
        HISTORY.write_text(json.dumps(h[-500:], ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def encode_seconds(path):
    """输出文件从创建到最后写入经过的秒数（≈转码耗时）。Linux 没有 Birth 时间，返回 None。"""
    st = Path(path).stat()
    birth = getattr(st, "st_birthtime", None)
    return round(st.st_mtime - birth, 1) if birth else None
