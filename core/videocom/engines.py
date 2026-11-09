"""
engines.py — "转码"这一步的可替换接口。

每个桶在 manifest["engine"] 里指定由谁处理：
  external:Aagedal / external:HandBrake  → VideoCom 不做事，等外部 App 把结果放进输出文件夹
  builtin:remux                          → VideoCom 自己用 ffmpeg 无损转封装（-c copy）
  builtin:encode                         → 预留：以后把一般视频的转码也收进来（方案 B），接口已定，未实现

后续步骤（匹配、补信息、校验、报告）只认"输出文件夹里有没有结果"，不关心是谁生成的，
所以以后把 external:Aagedal 换成 builtin:encode，其它代码不用改。
"""
from pathlib import Path

from . import config, util

DEFAULT_ENGINE = {
    "daily": {"compress": "external:Aagedal", "remux": "builtin:remux"},
    "movie": {"compress": "external:HandBrake", "remux": "builtin:remux"},
}


class Engine:
    name = ""
    external = True

    def run(self, cfg, line, entry, out_dir):
        """生成输出文件并返回路径；外部引擎不实现。"""
        raise NotImplementedError


class External(Engine):
    def __init__(self, app):
        self.name = f"external:{app}"
        self.app = app


class BuiltinRemux(Engine):
    name = "builtin:remux"
    external = False

    def run(self, cfg, line, entry, out_dir):
        ffmpeg = config.tool(cfg, "ffmpeg")
        if not ffmpeg:
            raise RuntimeError("找不到 ffmpeg")
        src = Path(entry["src_now"])
        ext = "." + cfg["target_container"][line]
        out = util.unique_path(Path(out_dir) / f"{src.stem}_remux{ext}")
        tmp = out.with_name(out.stem + ".videocom-part" + ext)
        if line == "daily":
            # MP4：主视频 + 全部音轨 + 文本字幕转 mov_text；data 轨（mebx/tmcd）放不进 MP4，会丢弃
            cmd = [ffmpeg, "-v", "error", "-y", "-i", src, "-map", "0:v:0", "-map", "0:a?",
                   "-c", "copy", "-tag:v", "hvc1", "-map_metadata", "0", "-movflags", "+use_metadata_tags"]
            if any(s.get("codec") in ("subrip", "ass", "ssa", "webvtt", "mov_text")
                   for s in entry.get("probe", {}).get("subs", [])):
                cmd += ["-map", "0:s?", "-c:s", "mov_text"]
        else:
            # MKV：全部轨道原样拷贝，含字幕、字体附件、章节；mov_text 字幕转 SRT；data 轨丢弃
            cmd = [ffmpeg, "-v", "error", "-y", "-i", src, "-map", "0", "-map", "-0:d", "-c", "copy",
                   "-map_metadata", "0", "-map_chapters", "0"]
            if any(s.get("codec") == "mov_text" for s in entry.get("probe", {}).get("subs", [])):
                cmd += ["-c:s", "srt"]
        r = util.run(cmd + [tmp])
        if r.returncode != 0:
            if tmp.exists():
                tmp.unlink()
            raise RuntimeError((r.stderr.strip() or "ffmpeg 失败")[-400:])
        tmp.rename(out)
        return out


class BuiltinEncode(Engine):
    """预留给方案 B：VideoCom 内置 ffmpeg 转码（可借鉴 videocrunch 的 SSIM 质量搜索）。"""
    name = "builtin:encode"
    external = False

    def run(self, cfg, line, entry, out_dir):
        raise NotImplementedError("builtin:encode 尚未实现，第一版请用 external:Aagedal")


def get(name):
    if name.startswith("external:"):
        return External(name.split(":", 1)[1])
    return {"builtin:remux": BuiltinRemux, "builtin:encode": BuiltinEncode}[name]()
