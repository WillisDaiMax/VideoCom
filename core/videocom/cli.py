"""
cli.py — 命令行入口：python3 -m videocom <命令> ...

  scan        选线别 + 源文件夹 + 批次根目录，只读扫描并给出分类（不动文件）
  show        查看批次（--json 输出完整 manifest，给界面用）
  set-bucket  手动改分类：--ids 3,7 --bucket review
  apply       确认后按分类移动文件，并执行内置转封装
  status      查看等待中的文件有多少已经有输出（只读）
  finish      匹配输出 → 一般视频补原信息 → 校验 → 报告（可重复运行）
  cleanup     把校验通过的原片移到废纸篓（不加 --yes 只列清单）
  undo        把还没处理完的原文件移回原位置
  report      重新生成报告

全局参数：--events 每行输出一个 JSON 事件（SwiftUI 壳用）；--config 指定配置文件。
"""
import argparse
import json
import sys
from pathlib import Path

from . import batch, config, util
from .config import BUCKET_LABEL


def _ids(s):
    out = set()
    for part in (s or "").split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        elif part:
            out.add(int(part))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="videocom", description="VideoCom 视频整理与转码收尾工具")
    ap.add_argument("--events", action="store_true", help="以 JSON 行输出事件")
    ap.add_argument("--config", help="配置文件路径")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("scan")
    p.add_argument("--line", required=True, choices=config.LINES)
    p.add_argument("--src", required=True, nargs="+", help="要整理的文件夹或文件，可多个")
    p.add_argument("--root", required=True, help="批次文件夹建在哪里")
    p.add_argument("--name", help="批次文件夹名（默认 VideoCom-线别-时间）")
    p.add_argument("--jobs", type=int, default=3)
    p.add_argument("--min-size-mb", type=float, help="小于多少 MB 不用压缩，0 = 不考虑大小（默认读配置）")
    for k in ("compress", "skip", "review", "remux", "output", "report"):
        p.add_argument(f"--dir-{k}", help=f"{k} 目录改到任意位置（默认在批次文件夹内）")

    for name in ("show", "apply", "status", "finish", "undo", "report"):
        q = sub.add_parser(name)
        q.add_argument("--batch", required=True)
        if name == "show":
            q.add_argument("--json", action="store_true")

    q = sub.add_parser("set-bucket")
    q.add_argument("--batch", required=True)
    q.add_argument("--ids", required=True, help="如 3,7,10-12")
    q.add_argument("--bucket", required=True, choices=config.BUCKETS)
    q.add_argument("--subgroup", help="仅一般视频要压缩：HDR / SDR")

    q = sub.add_parser("cleanup")
    q.add_argument("--batch", required=True)
    q.add_argument("--yes", action="store_true", help="真正移到废纸篓")
    q.add_argument("--include-warn", action="store_true", help="带提醒（非失败）的也清理")
    q.add_argument("--ids", help="只清理这些")
    q.add_argument("--trash-dir", help=argparse.SUPPRESS)   # 测试用

    a = ap.parse_args(argv)
    util.EVENTS = a.events
    cfg = config.load(a.config)
    try:
        if a.cmd == "scan":
            missing = [t for t in ("ffprobe",) if not config.tool(cfg, t)]
            if missing:
                raise RuntimeError(f"缺少工具：{missing}")
            if a.line == "daily" and not config.tool(cfg, "exiftool"):
                util.emit("warn", msg="找不到 exiftool：GPS/拍摄时间无法读取和写回（brew install exiftool）")
            if a.min_size_mb is not None:
                cfg["min_size_mb"] = max(0.0, a.min_size_mb)
            overrides = {k: getattr(a, f"dir_{k}") for k in ("compress", "skip", "review", "remux", "output", "report")}
            m = batch.scan(cfg, a.line, a.src, a.root, overrides, a.jobs, a.name)
            if not a.events:
                for b, n in batch.counts(m).items():
                    print(f"  {BUCKET_LABEL[b]:<6} {n:>5}")
                print(f"批次：{m['batch_dir']}\n确认分类后运行：python3 -m videocom apply --batch \"{m['batch_dir']}\"")
            return
        m = batch.load(a.batch)
        if a.cmd == "show":
            if a.json or a.events:
                print(json.dumps(m, ensure_ascii=False))
            else:
                print(f"{m['batch_dir']}  阶段：{m['stage']}")
                for e in m["entries"]:
                    print(f"{e['id']:>4}  {BUCKET_LABEL[e['bucket']]:<6} {e.get('subgroup',''):<4} {e['state']:<10} {e['name']}"
                          f"  — {'；'.join(e['reasons'][:2])}")
        elif a.cmd == "set-bucket":
            batch.set_bucket(m, _ids(a.ids), a.bucket, a.subgroup, cfg)
            util.emit("result", stage=m["stage"], counts=batch.counts(m))
        elif a.cmd == "apply":
            batch.apply(cfg, m)
            if not a.events:
                for b, w in batch.waiting_summary(m).items():
                    print(f"等待 {w['engine']}：{w['count']} 个，在 {w['dir']}")
                print(f"把转码输出放到：{m['dirs']['output']}\n完成后运行：python3 -m videocom finish --batch \"{m['batch_dir']}\"")
        elif a.cmd == "status":
            s = batch.status(cfg, m)
            util.emit("result", **s) if a.events else print(json.dumps(s, ensure_ascii=False, indent=1))
        elif a.cmd == "finish":
            paths = batch.finish(cfg, m)
            if not a.events:
                from . import report
                s = report.summary(m)
                print(f"通过 {s['passed']}（含提醒 {s['warn']}），节省 {s['saved_mb']} MB（{s['saved_pct']}%）")
                print(f"报告：{paths['html']}")
                if sys.platform == "darwin":
                    util.run(["open", paths["html"]])
        elif a.cmd == "cleanup":
            ids = _ids(a.ids) if a.ids else None
            cands = [e for e in batch.cleanup_candidates(m, a.include_warn) if ids is None or e["id"] in ids]
            if not a.yes:
                if a.events:
                    util.emit("result", stage="cleanup-preview", ids=[e["id"] for e in cands],
                              freed=sum(e["probe"]["size"] for e in cands))
                else:
                    for e in cands:
                        print(f"{e['id']:>4}  {e['src_now']}")
                    print(f"共 {len(cands)} 个，可释放 {sum(e['probe']['size'] for e in cands) / 2**30:.2f} GB。"
                          f"确认后加 --yes 移到废纸篓。")
                return
            batch.cleanup(cfg, m, ids, a.include_warn, a.trash_dir)
        elif a.cmd == "undo":
            n = batch.undo(cfg, m)
            if not a.events:
                print(f"已移回 {n} 个文件")
        elif a.cmd == "report":
            from . import report
            paths = report.write(cfg, m)
            util.emit("result", report=paths["html"]) if a.events else print(paths["html"])
    except Exception as ex:
        util.emit("error", msg=str(ex))
        sys.exit(1)
