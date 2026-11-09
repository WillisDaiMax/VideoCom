"""
batch.py — 批次流程。一个批次 = 一个文件夹 + 一份 videocom.json（manifest）。

阶段（stage）：
  scanned   扫描完，等你确认分类（此时还没动任何文件）
  moved     已按桶移动；等外部转码（Aagedal / HandBrake）
  finished  已匹配、补信息（一般视频）、校验并出报告；可重复运行，只处理新出现的输出
  cleaned   已把校验通过的原文件移到废纸篓

每个文件（entry）的 state：
  planned → moved → matched → verified / failed
  另有：unmatched（没找到输出）、writing（输出还在写）、kept（不用压缩 / 需人工确认，留在原桶）、trashed、restored_back（已撤销）
"""
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from . import classify, config, engines, estimate, meta, probe, util, verify
from .config import BUCKETS, MANIFEST_NAME

WAIT_BUCKETS = ("compress", "remux")   # 需要输出文件的桶


# ---------- manifest 读写 ----------
def load(batch_dir):
    p = Path(batch_dir) / MANIFEST_NAME
    if not p.is_file():
        raise FileNotFoundError(f"不是 VideoCom 批次文件夹：{batch_dir}")
    return json.loads(p.read_text(encoding="utf-8"))


def save(m):
    p = Path(m["batch_dir"]) / MANIFEST_NAME
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)   # 原子替换，中途断电也不会写坏


def _bucket_dir(m, e):
    d = Path(m["dirs"][e["bucket"]])
    return d / e["subgroup"] if e.get("subgroup") else d


# ---------- 1. 扫描 ----------
def discover(cfg, roots, skip_dirs):
    exts = set(cfg["scan_ext"])
    skip = {Path(s).resolve() for s in skip_dirs}
    for root in roots:
        root = Path(root)
        if root.is_file():
            yield root
            continue
        for dp, dns, fns in os.walk(root):
            dpp = Path(dp)
            dns[:] = [d for d in dns if d not in cfg["exclude_dirs"] and not d.startswith(".")
                      and (dpp / d).resolve() not in skip]
            for f in sorted(fns):
                p = dpp / f
                if not f.startswith("._") and p.suffix.lower() in exts and not p.is_symlink() \
                        and ".videocom-part" not in f:
                    yield p


def scan(cfg, line, sources, root, dir_overrides=None, jobs=3, name=None):
    """创建批次文件夹和 manifest，只读扫描，不移动任何文件。返回 manifest。"""
    if line not in config.LINES:
        raise ValueError(f"线别必须是 {config.LINES}")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    batch_dir = Path(root).expanduser().resolve() / (name or f"VideoCom-{line}-{stamp}")
    batch_dir.mkdir(parents=True, exist_ok=False)
    dirs = {k: str((batch_dir / v).resolve()) for k, v in cfg["dirs"].items()}
    for k, v in (dir_overrides or {}).items():
        if v:
            dirs[k] = str(Path(v).expanduser().resolve())
    files = list(discover(cfg, sources, [batch_dir, *dirs.values()]))
    util.emit("log", msg=f"发现 {len(files)} 个视频，开始扫描")
    m = {"version": config.MANIFEST_VERSION, "rules_version": config.RULES_VERSION, "line": line,
         "created": datetime.now().isoformat(timespec="seconds"), "batch_dir": str(batch_dir),
         "sources": [str(Path(s).resolve()) for s in sources], "dirs": dirs,
         "engine": engines.DEFAULT_ENGINE[line], "stage": "scanned", "entries": [], "log": []}

    def work(p):
        e = classify.classify(cfg, line, p)
        e.update(name=p.name, src_orig=str(p.resolve()), src_now=str(p.resolve()),
                 fs_times=util.fs_times(p), state="planned", output=None, checks={}, notes=[])
        return e

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        for i, e in enumerate(ex.map(work, files), 1):
            e["id"] = i
            m["entries"].append(e)
            util.emit("progress", stage="scan", done=i, total=len(files), name=e["name"])
    if files and not util.EVENTS:
        print()
    estimate.attach(cfg, m)
    save(m)
    util.emit("result", stage="scanned", batch=str(batch_dir), counts=counts(m))
    return m


def counts(m):
    c = {b: 0 for b in BUCKETS}
    for e in m["entries"]:
        c[e["bucket"]] += 1
    return c


# ---------- 2. 调整分类 ----------
def set_bucket(m, ids, bucket, subgroup=None, cfg=None):
    if m["stage"] != "scanned":
        raise RuntimeError("文件已经移动，不能再改分类（可先 undo）")
    if bucket not in BUCKETS:
        raise ValueError(f"桶必须是 {BUCKETS}")
    for e in m["entries"]:
        if e["id"] in ids:
            e["bucket"] = bucket
            if subgroup is not None:
                e["subgroup"] = subgroup
            elif bucket != "compress":
                e["subgroup"] = ""
            elif m["line"] == "movie" and (cfg or {}).get("movie_split_container", True) and e.get("probe"):
                e["subgroup"] = classify.movie_container(cfg or config.DEFAULTS, e["probe"])[0].upper()
            e["notes"].append(f"手动改为 {config.BUCKET_LABEL[bucket]}")
            if cfg:
                estimate.attach(cfg, m, [e])
    save(m)


# ---------- 3. 移动 ----------
def apply(cfg, m):
    if m["stage"] != "scanned":
        raise RuntimeError(f"当前阶段是 {m['stage']}，不能再移动")
    todo = [e for e in m["entries"] if e["state"] == "planned"]
    for i, e in enumerate(todo, 1):
        try:
            src = Path(e["src_now"])
            if not src.exists():
                raise FileNotFoundError("原文件不见了")
            dst = util.safe_move(cfg, src, _bucket_dir(m, e), e["fs_times"])
            e["src_now"] = str(dst)
            e["state"] = "moved" if e["bucket"] in WAIT_BUCKETS else "kept"
        except Exception as ex:
            e["state"] = "planned"
            e["notes"].append(f"移动失败：{ex}")
            util.emit("warn", msg=f"{e['name']} 移动失败：{ex}")
        util.emit("progress", stage="move", done=i, total=len(todo), name=e["name"])
        save(m)   # 每个文件都落盘，中途退出也能续上
    if todo and not util.EVENTS:
        print()
    Path(m["dirs"]["output"]).mkdir(parents=True, exist_ok=True)
    m["stage"] = "moved"
    save(m)
    run_builtin(cfg, m)
    util.emit("result", stage="moved", batch=m["batch_dir"], waiting=waiting_summary(m))


def run_builtin(cfg, m):
    """处理分给内置引擎的桶（第一版只有 remux）。"""
    for bucket, name in m["engine"].items():
        eng = engines.get(name)
        if eng.external:
            continue
        todo = [e for e in m["entries"] if e["bucket"] == bucket and e["state"] == "moved" and not e.get("output")]
        for i, e in enumerate(todo, 1):
            util.emit("progress", stage=name, done=i, total=len(todo), name=e["name"])
            try:
                e["builtin_output"] = str(eng.run(cfg, m["line"], e, m["dirs"]["output"]))
            except Exception as ex:
                e["notes"].append(f"{name} 失败：{ex}")
                util.emit("warn", msg=f"{e['name']} {name} 失败：{ex}")
            save(m)
        if todo and not util.EVENTS:
            print()


def waiting_summary(m):
    out = {}
    for b in WAIT_BUCKETS:
        es = [e for e in m["entries"] if e["bucket"] == b and e["state"] in ("moved", "unmatched", "writing")]
        if es:
            out[b] = {"engine": m["engine"].get(b), "count": len(es), "dir": str(Path(m["dirs"][b]))}
    return out


# ---------- 4. 匹配 ----------
def _outputs(cfg, m):
    root = Path(m["dirs"]["output"])
    exts = set(cfg["scan_ext"])
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in exts
                  and not p.name.startswith("._") and ".videocom-part" not in p.name)


def match(cfg, m, now=None):
    """给等待中的文件找输出。返回 {matched, writing, unmatched}。"""
    now = now or time.time()
    claimed = {e["output"] for e in m["entries"] if e.get("output")}
    outs = [o for o in _outputs(cfg, m) if str(o) not in claimed]
    pending = [e for e in m["entries"] if e["bucket"] in WAIT_BUCKETS and e["state"] in ("moved", "unmatched", "writing")]
    sufs = sorted(cfg["output_suffixes"], key=len, reverse=True)

    def score(e, o):
        stem, os_ = Path(e["src_now"]).stem.lower(), o.stem.lower()
        if os_ == stem:
            return 3
        rest = os_[len(stem):] if os_.startswith(stem) else None
        if rest is None:
            return 0
        if rest in [s.lower() for s in sufs]:
            return 2
        return 1 if re.match(r"^[ _\-.]", rest) else 0

    # 先分配精确/已知后缀的配对，再分配泛匹配，避免 IMG_1 抢走 IMG_1_2 的输出
    pairs = sorted(((score(e, o), e["id"], o) for e in pending for o in outs
                    if str(o) not in e.get("rejected", [])), key=lambda x: -x[0])
    taken_e, taken_o, res = set(), set(), {"matched": 0, "writing": 0, "unmatched": 0}
    by_id = {e["id"]: e for e in pending}
    for sc, eid, o in pairs:
        if sc == 0 or eid in taken_e or o in taken_o:
            continue
        e = by_id[eid]
        if now - o.stat().st_mtime < cfg["stable_seconds"]:
            e["state"] = "writing"
            taken_e.add(eid); taken_o.add(o)
            continue
        e["output"], e["state"] = str(o), "matched"
        e["encode_seconds"] = estimate.encode_seconds(o)   # 必须在写元数据/文件时间之前取
        taken_e.add(eid); taken_o.add(o)
    for e in pending:
        if e["id"] not in taken_e:
            e["state"] = "unmatched"
    for e in pending:
        res[{"matched": "matched", "writing": "writing"}.get(e["state"], "unmatched")] += 1
    save(m)
    return res


def status(cfg, m):
    """只看不改：等待中的文件有多少已经有输出。给界面轮询用。"""
    now = time.time()
    outs = _outputs(cfg, m)
    pending = [e for e in m["entries"] if e["bucket"] in WAIT_BUCKETS and e["state"] in ("moved", "unmatched", "writing")]
    stems = {}
    for o in outs:
        stems.setdefault(o.stem.lower(), []).append(o)
    found = writing = 0
    for e in pending:
        stem = Path(e["src_now"]).stem.lower()
        hits = [o for s, os_ in stems.items() if s == stem or (s.startswith(stem) and re.match(r"^[ _\-.]", s[len(stem):]))
                for o in os_]
        if hits:
            if any(now - o.stat().st_mtime < cfg["stable_seconds"] for o in hits):
                writing += 1
            else:
                found += 1
    done = sum(1 for e in m["entries"] if e["state"] in ("verified", "failed", "trashed"))
    return {"stage": m["stage"], "pending": len(pending), "ready": found, "writing": writing, "done": done,
            "counts": counts(m)}


# ---------- 5～7. 收尾：匹配 → 补信息 → 校验 ----------
def finish(cfg, m):
    if m["stage"] not in ("moved", "finished"):
        raise RuntimeError("请先完成移动")
    r = match(cfg, m)
    # 之前判失败的（例如旧版不认裁黑边）重新校验一次
    for e in m["entries"]:
        if e["state"] == "failed" and e.get("output") and Path(e["output"]).exists():
            e["state"] = "matched"
    todo = [e for e in m["entries"] if e["state"] == "matched"]
    util.emit("log", msg=f"匹配到 {r['matched']} 个输出，写入中 {r['writing']}，未找到 {r['unmatched']}")
    for i, e in enumerate(todo, 1):
        util.emit("progress", stage="finish", done=i, total=len(todo), name=e["name"])
        try:
            a = e["probe"]
            a["size"] = Path(e["src_now"]).stat().st_size
            b = probe.summarize(cfg, e["output"])
            checks = verify.compare(cfg, m["line"], a, b, e["bucket"], e.get("subgroup", ""))
            if not checks["时长"]["ok"]:
                # 时长对不上：很可能配错了，不写元数据，退回未匹配
                e.setdefault("rejected", []).append(e["output"])
                e["checks"], e["state"], e["output"] = checks, "unmatched", None
                e["notes"].append("候选输出时长不符，未采用")
                continue
            if m["line"] == "daily":
                checks.update(meta.restore(cfg, e))   # 文件系统时间在这里最后写
                b["size"] = Path(e["output"]).stat().st_size
            e["out_probe"] = b
            e["checks"] = checks
            e["state"], e["has_warn"] = verify.verdict(checks)
            if e["state"] == "verified" and not e.get("learned"):
                estimate.learn(cfg, m, e)
                e["learned"] = True
        except Exception as ex:
            e["state"] = "failed"
            e["checks"] = {"处理": {"ok": False, "level": "fail", "detail": str(ex)[:300]}}
        save(m)
    if todo and not util.EVENTS:
        print()
    m["stage"] = "finished"
    save(m)
    from . import report
    paths = report.write(cfg, m)
    util.emit("result", stage="finished", report=paths["html"], summary=report.summary(m))
    return paths


# ---------- 8. 清理 ----------
def cleanup_candidates(m, include_warn=False):
    return [e for e in m["entries"] if e["state"] == "verified" and (include_warn or not e.get("has_warn"))
            and e.get("output") and Path(e["src_now"]).exists()
            and Path(e["output"]).stat().st_size < Path(e["src_now"]).stat().st_size * (1.02 if e["bucket"] == "remux" else 1)]


def cleanup(cfg, m, ids=None, include_warn=False, trash_dir=None):
    cands = [e for e in cleanup_candidates(m, include_warn) if ids is None or e["id"] in ids]
    res = util.trash([e["src_now"] for e in cands], trash_dir)
    n = 0
    for e in cands:
        err = res.get(e["src_now"], "未处理")
        if err:
            e["notes"].append(f"移到废纸篓失败：{err}")
        else:
            e["state"] = "trashed"; n += 1
    if n:
        m["stage"] = "cleaned"
    save(m)
    from . import report
    report.write(cfg, m)
    util.emit("result", stage="cleaned", trashed=n, failed=len(cands) - n,
              freed=sum(e["probe"]["size"] for e in cands if e["state"] == "trashed"))
    return n


# ---------- 撤销移动 ----------
def undo(cfg, m):
    """把还没处理完的原文件移回原位置（已校验、已清理的不动）。"""
    n = 0
    for e in m["entries"]:
        if e["state"] not in ("moved", "kept", "unmatched", "writing"):
            continue
        cur, orig = Path(e["src_now"]), Path(e["src_orig"])
        if not cur.exists() or cur == orig:
            continue
        try:
            dst = util.safe_move(cfg, cur, orig.parent, e["fs_times"], orig.name)
            if dst.name != orig.name:
                e["notes"].append(f"原位置已有同名文件，退回为 {dst.name}")
            e["src_now"], e["state"] = str(dst), "planned"
            n += 1
        except Exception as ex:
            e["notes"].append(f"撤销失败：{ex}")
        save(m)
    if all(e["state"] in ("planned",) for e in m["entries"]):
        m["stage"] = "scanned"
    save(m)
    util.emit("result", stage=m["stage"], restored=n)
    return n
