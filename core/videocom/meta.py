"""
meta.py — 一般视频线：把原视频的 GPS、拍摄时间写回输出文件，最后写文件系统时间。
逻辑沿用 line1-daily/restore_meta.py，只是改成按 manifest 里的配对和扫描时记录的时间来写。

顺序很重要：exiftool 重写文件会改 mtime/Birth，所以文件系统时间必须最后写，之后不能再动输出文件。
"""
import json

from . import config, util

ET_API = ["-api", "QuickTimeUTC=1", "-api", "LargeFileSupport=1"]


DATE_TAGS = ["QuickTime:CreateDate", "QuickTime:ModifyDate",
             "TrackCreateDate", "TrackModifyDate", "MediaCreateDate", "MediaModifyDate"]  # 不带分组 = 每条轨道都写


def copy_tags(cfg, src, dst):
    """
    两步写入：
    1) 删掉输出里已有的 Keys。ffmpeg 的 -movflags +use_metadata_tags 把 Keys 写在 moov/udta/meta，
       iPhone「照片」只认 moov/meta，放在 udta 里的拍摄时间和位置会被忽略（2026-11-09 用 IMG_1035 实测确认）。
       不先删，exiftool 会沿用 udta 里的位置原地改写。
    2) 从原片拷全部标签，Keys 由 exiftool 写到 moov/meta；
    3) mvhd/tkhd/mdhd 日期改成拍摄时间（Keys:CreationDate 转 UTC）。
       原片如果是从「照片」导出/隔空投送来的，这些日期是导出时间；照片在读不到 Keys 时会退回用它。
    """
    exe = config.tool(cfg, "exiftool")
    if not exe:
        return False, "找不到 exiftool"
    r0 = util.run([exe, "-overwrite_original", "-Keys:all=", dst])
    if r0.returncode not in (0, 1):
        return False, r0.stderr.strip() or "清除旧 Keys 失败"
    r = util.run([exe, *ET_API, "-overwrite_original",
                  "-tagsFromFile", src,
                  "-all:all",                         # Keys / UserData / ItemList / mvhd·tkhd·mdhd 日期，按原分组写回
                  "--Rotation", "--MatrixStructure",  # 转码器已把旋转烧进画面，再拷会二次旋转
                  "--MajorBrand", "--MinorVersion", "--CompatibleBrands",  # 别把原片的 ftyp 当成 Keys 写进去
                  "-UserData:GPSCoordinates<Keys:GPSCoordinates",  # 额外写 ©xyz，兼容 Google 相册 / ffprobe
                  dst])
    errors = [l for l in r.stderr.splitlines() if l.startswith("Error")]
    if errors or r.returncode not in (0, 1):
        return False, r.stderr.strip() or r.stdout.strip()
    # 3) 用输出文件自己的 Keys:CreationDate 改 mvhd/tkhd/mdhd（在 -tagsFromFile 里写不到每条轨道，只能单独一步）
    if read_meta(cfg, dst).get("CreationDate"):
        r3 = util.run([exe, *ET_API, "-overwrite_original", *[f"-{t}<Keys:CreationDate" for t in DATE_TAGS], dst])
        if r3.returncode not in (0, 1):
            return False, r3.stderr.strip()
    return True, r.stderr.strip() or r.stdout.strip()


def _boxes(f, start, end):
    """遍历 [start, end) 内的 MP4/MOV box，产出 (type, 内容起点, 内容终点)。"""
    pos = start
    while pos + 8 <= end:
        f.seek(pos)
        hdr = f.read(8)
        size, typ = int.from_bytes(hdr[:4], "big"), hdr[4:8].decode("latin-1")
        head = 8
        if size == 1:
            size, head = int.from_bytes(f.read(8), "big"), 16
        elif size == 0:
            size = end - pos
        if size < head:
            return
        yield typ, pos + head, pos + size
        pos += size


def apple_keys(path):
    """
    返回 moov/meta/keys 里的键名集合（iPhone「照片」读的位置）。
    读不到返回空集合。注意：udta/meta 里的 Keys 不算。
    """
    names = set()
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            moov = next(((a, b) for t, a, b in _boxes(f, 0, size) if t == "moov"), None)
            if not moov:
                return names
            for t, a, b in _boxes(f, *moov):
                if t != "meta":
                    continue
                f.seek(a + 4)
                if f.read(4) != b"hdlr":   # ISO 风格 meta 带 4 字节 version/flags
                    a += 4
                for t2, a2, b2 in _boxes(f, a, b):
                    if t2 != "keys":
                        continue
                    f.seek(a2 + 4)
                    n = int.from_bytes(f.read(4), "big")
                    for _ in range(n):
                        ksize = int.from_bytes(f.read(4), "big")
                        f.read(4)   # namespace，通常是 mdta
                        names.add(f.read(max(0, ksize - 8)).decode("utf-8", "replace"))
    except (OSError, ValueError):
        pass
    return names


def read_meta(cfg, p):
    exe = config.tool(cfg, "exiftool")
    if not exe:
        return {}
    r = util.run([exe, *ET_API, "-j", "-n", "-GPSLatitude", "-GPSLongitude", "-QuickTime:CreateDate", "-Keys:CreationDate", p])
    try:
        return json.loads(r.stdout)[0]
    except Exception:
        return {}


def _gps(m):
    lat, lon = m.get("GPSLatitude"), m.get("GPSLongitude")
    return None if lat is None or lon is None else (round(float(lat), 4), round(float(lon), 4))


def restore(cfg, entry):
    """返回 checks 片段：{名称: {ok, level, detail}}。"""
    src, dst = entry["src_now"], entry["output"]
    checks = {}
    ok_tags, msg = copy_tags(cfg, src, dst)
    if not ok_tags:
        checks["写入元数据"] = {"ok": False, "level": "fail", "detail": msg[:300]}
    ok_fs, msg_fs = util.apply_fs_times(cfg, dst, entry["fs_times"])   # 必须最后
    a, b = read_meta(cfg, src), read_meta(cfg, dst)
    ga, gb = _gps(a), _gps(b)
    checks["GPS"] = {"ok": ga == gb, "level": "fail",
                     "detail": ("原文件无 GPS" if ga is None and gb is None else f"{ga} → {gb}")}
    ca, cb = a.get("CreationDate"), b.get("CreationDate")
    if ca:
        ok_date = (ca == cb)
        detail = f"{ca} → {cb}"
    else:   # 原片没有 Keys:CreationDate，退回比较 mvhd 日期
        ca, cb = a.get("CreateDate"), b.get("CreateDate")
        ok_date = (ca == cb)
        detail = f"{ca} → {cb}" if ca and not str(ca).startswith("0000") else "原文件无拍摄时间"
    checks["拍摄时间"] = {"ok": ok_date, "level": "fail", "detail": detail}
    # iPhone「照片」只读 moov/meta 里的 Keys：值对了但位置不对，照片里一样看不到
    need = set()
    if a.get("CreationDate"):
        need.add("com.apple.quicktime.creationdate")
    if ga is not None:
        need.add("com.apple.quicktime.location.ISO6709")
    if need:
        missing = need - apple_keys(dst)
        checks["照片可识别"] = {"ok": not missing, "level": "fail",
                            "detail": "拍摄时间、位置在 moov/meta" if not missing
                            else "不在 moov/meta：" + "、".join(sorted(k.split(".")[-1] for k in missing))}
    fs_ok = ok_fs and util.fs_times_match(dst, entry["fs_times"])
    checks["文件时间"] = {"ok": fs_ok, "level": "fail", "detail": msg_fs or ("一致" if fs_ok else "不一致")}
    return checks
