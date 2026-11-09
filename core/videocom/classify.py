"""
classify.py — 按线别把单个文件分进 4 个桶：compress / skip / review / remux。

线别由用户在开始时选定（一般视频 / 电影），这里不再猜线别，
只在文件明显像另一条线时给出提示。规则阈值都在 config.py。
"""
from pathlib import Path

from . import probe


def _tags(s, meta):
    t = []
    if s.get("dv_profile") is not None:
        t.append(f"Dolby Vision P{s['dv_profile']}")
    if s.get("hdr"):
        t.append(s["hdr"])
    if s.get("bit_depth") == 10:
        t.append("10-bit")
    if s.get("vfr"):
        t.append("VFR")
    if s.get("rotation"):
        t.append("Rotation")
    if len(s.get("audio", [])) > 1:
        t.append("多音轨")
    if any(a.get("codec") == "apac" or a.get("codec") is None for a in s.get("audio", [])):
        t.append("空间音频/未知音频")
    subs = s.get("subs", [])
    if subs:
        t.append("字幕:" + "/".join(sorted({x.get("codec") or "?" for x in subs})))
    if any(x.get("codec") in probe.IMAGE_SUBS for x in subs):
        t.append("图像字幕")
    if s.get("chapters"):
        t.append("章节")
    if s.get("attachments"):
        t.append("字体/附件")
    if s.get("video_tracks", 0) > 1:
        t.append("多视频轨")
    if meta.get("GPSLatitude") is not None:
        t.append("GPS")
    return t


REASONS_ZH = {
    "read_failed": "读取失败：{err}",
    "no_video": "没有视频流（纯音频或文件损坏）",
    "master": "{codec} 是母版/中间格式，先决定是否保留母版",
    "legacy_small": "{codec}，但只有 {mb} MB，收益有限",
    "legacy_lowbr": "{codec}，但码率已很低（bpp {bpp}），收益有限",
    "to_hevc": "{codec} → HEVC（bpp {bpp}）",
    "efficient_big": "已是 {codec}，但 bpp {bpp} > {hi}，体积仍大",
    "remux": "HEVC 码率合理，只需封装为 {target}（不重编码）",
    "efficient_ok": "已是高效编码 {codec}（bpp {bpp}）",
    "unusual_codec": "不常见编码 {codec}",
    "spatial_review": "有空间音频或无法识别的音轨，转码/转封装会丢失",
    "spatial_drop": "空间音频轨会丢，保留立体声 AAC",
    "image_subs": "MP4 放不下 PGS/VobSub 图像字幕，可能应该走电影线",
    "dv_remux": "Dolby Vision 转封装 MP4 的兼容性需确认",
    "dv_p7": "Dolby Vision Profile 7：HandBrake 只保留基层并转为 8.1",
    "ass_fonts": "ASS 特效字幕带字体附件，转码后字体是否保留需确认",
    "hdr_tonemap": "HDR → 8-bit 需要带色调映射的预设",
    "hint_movie": "提示：这个文件更像电影资源",
    "hint_daily": "提示：这个文件像手机/相机拍摄",
    "br_estimated": "视频码率为估算值",
    "movie_mp4": "没有字幕和附件，输出 MP4（Apple 设备可直接播放）",
    "movie_mkv_subs": "有字幕，输出 MKV",
    "movie_mkv_fonts": "有字体附件，输出 MKV",
    "movie_mkv_audio": "音轨 {codecs} 放不进 MP4，输出 MKV",
}


def movie_container(cfg, s):
    """电影线：没有字幕、没有附件、音轨 MP4 都放得下 → mp4；否则 mkv。返回 (容器, [(原因代码, 参数)])。"""
    why = []
    if s.get("subs"):
        why.append(("movie_mkv_subs", {}))
    if s.get("attachments"):
        why.append(("movie_mkv_fonts", {}))
    bad = sorted({a.get("codec") or "?" for a in s.get("audio", [])} - set(cfg.get("movie_mp4_audio", [])))
    if bad:
        why.append(("movie_mkv_audio", {"codecs": "/".join(bad)}))
    return ("mkv", why) if why else ("mp4", [])


def classify(cfg, line, path):
    path = Path(path)
    rec = {"tags": [], "reasons": [], "reason_codes": [], "subgroup": ""}
    try:
        s = probe.summarize(cfg, path)
    except Exception as e:
        rec.update(bucket="review", reasons=[f"读取失败：{e}"], reason_codes=[{"k": "read_failed", "p": {"err": str(e)[:200]}}],
                   probe={"size": path.stat().st_size})
        return rec
    meta = probe.exif_meta(cfg, path)   # 只对 MOV/MP4 系容器生效，其它返回 {}
    rec["probe"], rec["exif"] = s, meta
    T, R = _tags(s, meta), rec["reasons"]
    RC = rec["reason_codes"]

    def add(key, **p):
        """原因：中文文本（CLI/报告用）+ 代码与参数（界面按语言自己翻译）"""
        R.append(REASONS_ZH[key].format(**p))
        RC.append({"k": key, "p": p})
    rec["tags"] = T
    if not s.get("codec"):
        rec["bucket"] = "review"
        add("no_video")
        return rec

    codec, bpp = s["codec"], s.get("bpp")
    size_mb = s["size"] / 2**20
    target = cfg["target_container"][line]
    # 按扩展名判断容器：ffprobe 对 MOV 和 MP4 报同一个 format_name，分不出来
    in_target = path.suffix.lower() in {"mp4": (".mp4", ".m4v"), "mkv": (".mkv",)}[target]
    split = line == "movie" and cfg.get("movie_split_container", True)
    if split and movie_container(cfg, s)[0] == "mp4" and path.suffix.lower() in (".mp4", ".m4v"):
        in_target = True      # 无字幕的电影本来就是 MP4：HEVC 不必再转封装成 MKV
    hi = cfg["bpp_efficient_high"][line]

    # ---- 基础判定 ----
    if codec in cfg["master_codecs"]:
        bucket = "review"; add("master", codec=codec)
    elif codec in cfg["legacy_codecs"]:
        if cfg["min_size_mb"] > 0 and size_mb < cfg["min_size_mb"]:
            bucket = "skip"; add("legacy_small", codec=codec, mb=round(size_mb, 1))
        elif bpp is not None and bpp < cfg["bpp_low"]:
            bucket = "skip"; add("legacy_lowbr", codec=codec, bpp=bpp)
        else:
            bucket = "compress"; add("to_hevc", codec=codec, bpp=bpp)
    elif codec in cfg["efficient_codecs"]:
        if bpp is not None and bpp > hi and size_mb >= cfg["min_size_mb"]:
            bucket = "compress"; add("efficient_big", codec=codec, bpp=bpp, hi=hi)
        elif not in_target and codec == "hevc":
            bucket = "remux"; add("remux", target=target.upper())
        else:
            bucket = "skip"; add("efficient_ok", codec=codec, bpp=bpp)
    else:
        bucket = "review"; add("unusual_codec", codec=codec)

    # ---- 有丢失风险时升级为人工确认 ----
    if bucket in ("compress", "remux"):
        if line == "daily":
            auds = s.get("audio", [])
            has_normal = any(x.get("codec") not in (None, "apac") for x in auds)
            if "空间音频/未知音频" in T and (cfg.get("daily_review", {}).get("spatial_audio", True) or not has_normal):
                bucket = "review"; add("spatial_review")
            elif "空间音频/未知音频" in T:
                add("spatial_drop")
            elif "图像字幕" in T:
                bucket = "review"; add("image_subs")
            elif bucket == "remux" and s.get("dv_profile") is not None:
                bucket = "review"; add("dv_remux")
        else:
            mr = cfg["movie_review"]
            if mr.get("dv_profile7") and str(s.get("dv_profile")) == "7":
                bucket = "review"; add("dv_p7")
            elif mr.get("ass_with_fonts") and s.get("attachments") and \
                    any(x.get("codec") in ("ass", "ssa") for x in s.get("subs", [])):
                bucket = "review"; add("ass_fonts")

    # ---- 一般视频：HDR 提示（可选按 HDR/SDR 分子文件夹） ----
    is_hdr = bool(s.get("hdr") or s.get("dv_profile") is not None)
    if bucket == "compress" and line == "daily":
        if cfg.get("daily_split_hdr"):
            rec["subgroup"] = "HDR" if is_hdr else "SDR"
        if is_hdr:
            add("hdr_tonemap")

    # ---- 电影：按字幕分 MP4 / MKV 两个子文件夹，方便在 HandBrake 里用两个预设 ----
    if bucket == "compress" and split:
        c, why = movie_container(cfg, s)
        rec["subgroup"] = c.upper()
        if c == "mp4":
            add("movie_mp4")
        for k, p in why:
            add(k, **p)

    # ---- 线别提示（不改桶） ----
    if line == "daily" and (s.get("attachments") or len(s.get("subs", [])) > 1 or s["duration"] > 40 * 60):
        add("hint_movie")
    if line == "movie" and ("GPS" in T or meta.get("Make")):
        add("hint_daily")
    if s.get("vbitrate_estimated"):
        add("br_estimated")
    rec["bucket"] = bucket
    return rec
