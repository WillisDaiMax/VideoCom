"""
verify.py — 原片 vs 输出的对比校验。

level=fail：不通过（不进清理候选）；level=warn：提醒但不算失败。
两条线共用：时长、分辨率、体积；电影线重点比轨道清单；一般视频线的元数据校验在 meta.py。
"""
from collections import Counter


def _dims_ok(a, b):
    """原样、旋转 90°（宽高互换）、等比缩小都算对。返回 (ok, 说明)。"""
    aw, ah, bw, bh = a.get("width", 0), a.get("height", 0), b.get("width", 0), b.get("height", 0)
    if not (aw and ah and bw and bh):
        return False, "读不到分辨率"
    if (aw, ah) == (bw, bh):
        return True, f"{aw}×{ah}"
    if (aw, ah) == (bh, bw):
        return True, f"{aw}×{ah} → {bw}×{bh}（旋转已烧入）"
    for (w, h) in ((bw, bh), (bh, bw)):
        if w <= aw and h <= ah and abs(aw / ah - w / h) < 0.02:
            return True, f"{aw}×{ah} → {bw}×{bh}（已缩放）"
    return False, f"{aw}×{ah} → {bw}×{bh}"


def compare(cfg, line, a, b, bucket="compress"):
    """a=原片 probe，b=输出 probe。返回 checks。转封装（remux）体积允许 +2%。"""
    c = {}
    tol = max(cfg["duration_tolerance_s"], a.get("duration", 0) * cfg["duration_tolerance_pct"] / 100)
    dd = abs(a.get("duration", 0) - b.get("duration", 0))
    c["时长"] = {"ok": dd <= tol, "level": "fail", "detail": f"相差 {dd:.2f}s"}
    ok, d = _dims_ok(a, b)
    c["分辨率"] = {"ok": ok, "level": "fail", "detail": d}
    sa, sb = a.get("size", 0), b.get("size", 0)
    size_ok = sb <= sa * 1.02 if bucket == "remux" else sb < sa
    c["体积"] = {"ok": size_ok, "level": "warn",
                 "detail": f"{sa / 2**20:.1f} → {sb / 2**20:.1f} MB" + ("" if size_ok else "（输出比原片还大）")}
    if b.get("codec") not in ("hevc", "av1"):
        c["编码"] = {"ok": False, "level": "warn", "detail": f"输出编码是 {b.get('codec')}"}

    na, nb = len(a.get("audio", [])), len(b.get("audio", []))
    if line == "daily":
        c["音轨"] = {"ok": nb >= na, "level": "warn", "detail": f"{na} → {nb}"}
        return c

    # ---- 电影：轨道清单 ----
    la = Counter(x["lang"] for x in a.get("audio", []))
    lb = Counter(x["lang"] for x in b.get("audio", []))
    c["音轨"] = {"ok": nb >= na and not (la - lb), "level": "fail",
                 "detail": f"{na} → {nb}" + (f"，缺 {dict(la - lb)}" if la - lb else "")}
    sa_ = Counter(x["lang"] for x in a.get("subs", []))
    sb_ = Counter(x["lang"] for x in b.get("subs", []))
    ns_a, ns_b = len(a.get("subs", [])), len(b.get("subs", []))
    c["字幕"] = {"ok": ns_b >= ns_a and not (sa_ - sb_), "level": "fail",
                 "detail": f"{ns_a} → {ns_b}" + (f"，缺 {dict(sa_ - sb_)}" if sa_ - sb_ else "")}
    fa, fb = len(a.get("attachments", [])), len(b.get("attachments", []))
    if fa:
        c["字体附件"] = {"ok": fb >= fa, "level": "warn", "detail": f"{fa} → {fb}"}
    if a.get("chapters"):
        c["章节"] = {"ok": b.get("chapters", 0) >= a["chapters"], "level": "warn",
                     "detail": f"{a['chapters']} → {b.get('chapters', 0)}"}
    if a.get("hdr"):
        c["HDR"] = {"ok": b.get("hdr") == a["hdr"], "level": "warn", "detail": f"{a['hdr']} → {b.get('hdr') or 'SDR'}"}
    if a.get("dv_profile") is not None:
        c["Dolby Vision"] = {"ok": b.get("dv_profile") is not None, "level": "warn",
                             "detail": f"P{a['dv_profile']} → " + (f"P{b['dv_profile']}" if b.get("dv_profile") is not None else "无")}
    return c


def verdict(checks):
    """返回 (state, 是否有提醒)。"""
    fails = [k for k, v in checks.items() if v["level"] == "fail" and not v["ok"]]
    warns = [k for k, v in checks.items() if v["level"] == "warn" and not v["ok"]]
    return ("failed" if fails else "verified"), bool(warns)
