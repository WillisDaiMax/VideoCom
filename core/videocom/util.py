"""
util.py — 事件输出、文件时间、安全移动。

事件：--events 时每行输出一个 JSON（SwiftUI 壳读取）；否则输出给人看的文字。
"""
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from . import config

EVENTS = False


def emit(kind, **kw):
    """kind: log / progress / warn / error / result"""
    if EVENTS:
        print(json.dumps({"type": kind, **kw}, ensure_ascii=False), flush=True)
        return
    if kind == "progress":
        print(f"\r[{kw.get('done')}/{kw.get('total')}] {str(kw.get('name', ''))[:60]:<60}", end="", flush=True)
    elif kind == "result":
        pass
    else:
        prefix = {"warn": "[注意] ", "error": "[错误] "}.get(kind, "")
        print(prefix + str(kw.get("msg", "")), flush=True)


def run(cmd, timeout=None):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, timeout=timeout)


# ---------- 文件系统时间 ----------
def fs_times(p):
    st = os.stat(p)
    return {"birth": getattr(st, "st_birthtime", None), "mtime_ns": st.st_mtime_ns, "atime_ns": st.st_atime_ns}


def apply_fs_times(cfg, dst, times):
    """把记录的时间写到 dst。顺序：先 mtime/atime，再 Birth（APFS 会把晚于 mtime 的 Birth 拉回）。
    返回 (ok, 说明)。非 macOS 或没有 SetFile 时只写 mtime/atime。"""
    os.utime(dst, ns=(times["atime_ns"], times["mtime_ns"]))
    birth = times.get("birth")
    if birth is None:
        return True, ""
    setfile = config.tool(cfg, "setfile")
    if not setfile or sys.platform != "darwin":
        return False, "没有 SetFile，Birth 时间未写（xcode-select --install）"
    r = run([setfile, "-d", datetime.fromtimestamp(birth).strftime("%m/%d/%Y %H:%M:%S"), dst])
    os.utime(dst, ns=(times["atime_ns"], times["mtime_ns"]))   # SetFile 不动 mtime，这里再保险一次
    return r.returncode == 0, r.stderr.strip()


def fs_times_match(dst, times):
    st = os.stat(dst)
    ok_m = st.st_mtime_ns // 1000 == times["mtime_ns"] // 1000   # 微秒级比较，避免个别文件系统截断纳秒
    b = getattr(st, "st_birthtime", None)
    ok_b = times.get("birth") is None or b is None or int(b) == int(times["birth"])
    return ok_m and ok_b


# ---------- 移动 ----------
def unique_path(dst):
    dst = Path(dst)
    if not dst.exists():
        return dst
    n = 2
    while True:
        cand = dst.with_name(f"{dst.stem}_{n}{dst.suffix}")
        if not cand.exists():
            return cand
        n += 1


def same_volume(a, b):
    return os.stat(a).st_dev == os.stat(b).st_dev


def safe_move(cfg, src, dst_dir, times, name=None):
    """移动文件，重名自动加 _2/_3，绝不覆盖。返回新路径。
    同一卷：rename（瞬间完成，时间不变）。跨卷：复制 → 校验大小 → 写回时间 → 删除原文件。"""
    src, dst_dir = Path(src), Path(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = unique_path(dst_dir / (name or src.name))
    if same_volume(src, dst_dir):
        os.rename(src, dst)
        return dst
    tmp = dst.with_name(dst.name + ".videocom-part")
    shutil.copy2(src, tmp)
    if os.path.getsize(tmp) != os.path.getsize(src):
        os.remove(tmp)
        raise IOError("跨卷复制后大小不一致，已取消")
    os.rename(tmp, dst)
    apply_fs_times(cfg, dst, times)
    os.remove(src)
    return dst


def trash(paths, trash_dir=None):
    """移到废纸篓。macOS 用 Finder（可"放回原处"）；测试或非 macOS 时移到 trash_dir。返回 {路径: 错误或 ''}。"""
    res = {}
    if trash_dir or sys.platform != "darwin":
        td = Path(trash_dir or Path.home() / ".videocom-trash")
        td.mkdir(parents=True, exist_ok=True)
        for p in paths:
            try:
                shutil.move(str(p), str(unique_path(td / Path(p).name)))
                res[str(p)] = ""
            except Exception as e:
                res[str(p)] = str(e)
        return res
    for p in paths:
        esc = str(p).replace("\\", "\\\\").replace('"', '\\"')
        r = run(["osascript", "-e", f'tell application "Finder" to delete (POSIX file "{esc}" as alias)'])
        res[str(p)] = "" if r.returncode == 0 else (r.stderr.strip() or "Finder 删除失败")
    return res
