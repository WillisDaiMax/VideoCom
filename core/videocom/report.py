"""
report.py — 对比与结果报告：report.html（自包含，可筛选）+ report.csv。
异常（未匹配、校验失败、输出比原片大）排在最前面。
"""
import csv
import html
import json
from datetime import datetime
from pathlib import Path

from .config import BUCKET_LABEL, LINE_LABEL

STATE_LABEL = {"planned": "未移动", "moved": "等待转码", "writing": "输出写入中", "unmatched": "未找到输出",
               "matched": "已匹配", "verified": "通过", "failed": "未通过", "kept": "保留", "trashed": "原片已清理"}


def _mb(n):
    return round((n or 0) / 2**20, 1)


def summary(m):
    es = m["entries"]
    done = [e for e in es if e["state"] in ("verified", "trashed") and e.get("out_probe")]
    before = sum(e["probe"].get("size", 0) for e in done)
    after = sum(e["out_probe"].get("size", 0) for e in done)
    return {
        "total": len(es),
        "by_bucket": {b: sum(1 for e in es if e["bucket"] == b) for b in BUCKET_LABEL},
        "by_state": {s: sum(1 for e in es if e["state"] == s) for s in STATE_LABEL if any(e["state"] == s for e in es)},
        "passed": len(done), "warn": sum(1 for e in done if e.get("has_warn")),
        "before_mb": _mb(before), "after_mb": _mb(after), "saved_mb": _mb(before - after),
        "saved_pct": round((before - after) / before * 100, 1) if before else 0,
        "trashed": sum(1 for e in es if e["state"] == "trashed"),
    }


def _row(e):
    a, b = e.get("probe", {}), e.get("out_probe") or {}
    fails = [f"{k}：{v['detail']}" for k, v in e.get("checks", {}).items() if not v["ok"] and v["level"] == "fail"]
    warns = [f"{k}：{v['detail']}" for k, v in e.get("checks", {}).items() if not v["ok"] and v["level"] == "warn"]
    big = bool(b) and b.get("size", 0) >= a.get("size", 1) * (1.02 if e["bucket"] == "remux" else 1)
    anomaly = e["state"] in ("failed", "unmatched") or big
    return {
        "id": e["id"], "name": e["name"], "bucket": BUCKET_LABEL.get(e["bucket"], e["bucket"]),
        "subgroup": e.get("subgroup", ""), "state": STATE_LABEL.get(e["state"], e["state"]),
        "anomaly": anomaly, "codec": a.get("codec") or "", "res": f"{a.get('width', '')}×{a.get('height', '')}" if a.get("width") else "",
        "before_mb": _mb(a.get("size")), "after_mb": _mb(b.get("size")) if b else "",
        "ratio": f"{b['size'] / a['size'] * 100:.0f}%" if b and a.get("size") else "",
        "fails": fails, "warns": warns, "tags": e.get("tags", []), "reasons": e.get("reasons", []) + e.get("notes", []),
        "src": e.get("src_now", ""), "out": e.get("output") or "",
        "checks": {k: ("✓" if v["ok"] else ("✗" if v["level"] == "fail" else "!")) for k, v in e.get("checks", {}).items()},
    }


HTML = """<!doctype html><html lang="zh"><meta charset="utf-8"><title>VideoCom 报告</title>
<style>
body{font:13px -apple-system,"PingFang SC",sans-serif;margin:20px;color:#222}
.sum span{display:inline-block;margin:0 10px 8px 0;padding:6px 10px;background:#f2f2f2;border-radius:6px}
table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #e5e5e5;padding:5px 6px;text-align:left;vertical-align:top}
th{position:sticky;top:0;background:#fff}td.s{color:#666;font-size:12px}tr.bad{background:#fff3f0}
.tag{display:inline-block;background:#eef;border-radius:4px;padding:0 4px;margin:1px;font-size:11px}
.f{color:#c00}.w{color:#a60}.bar{margin:10px 0}select,input{margin-right:8px}
</style>
<h2>VideoCom 报告 · __LINE__ <small>__TIME__</small></h2><div class="sum">__SUM__</div>
<div class="bar">状态 <select id="fs"><option value="">全部</option></select>
分类 <select id="fb"><option value="">全部</option></select>
<label><input type="checkbox" id="fa">只看异常</label><input id="fq" placeholder="搜索文件名" size="24"></div>
<table><thead><tr><th>#</th><th>文件</th><th>分类</th><th>状态</th><th>编码</th><th>分辨率</th><th>原 MB</th><th>新 MB</th><th>比例</th><th>校验</th><th>问题</th><th>说明</th></tr></thead>
<tbody id="tb"></tbody></table>
<script>
const D=__DATA__;const fs=document.getElementById("fs"),fb=document.getElementById("fb"),fa=document.getElementById("fa"),fq=document.getElementById("fq");
[...new Set(D.map(r=>r.state))].forEach(s=>fs.add(new Option(s,s)));[...new Set(D.map(r=>r.bucket))].forEach(s=>fb.add(new Option(s,s)));
const e=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function draw(){const q=fq.value.toLowerCase();document.getElementById("tb").innerHTML=D.filter(r=>(!fs.value||r.state==fs.value)&&(!fb.value||r.bucket==fb.value)&&(!fa.checked||r.anomaly)&&(!q||r.name.toLowerCase().includes(q)))
.map(r=>`<tr class="${r.anomaly?"bad":""}"><td>${r.id}</td><td title="${e(r.src)}${r.out?"\\n→ "+e(r.out):""}">${e(r.name)}</td><td>${e(r.bucket)}${r.subgroup?" · "+e(r.subgroup):""}</td><td>${e(r.state)}</td><td>${e(r.codec)}</td><td>${e(r.res)}</td><td>${r.before_mb}</td><td>${r.after_mb}</td><td>${r.ratio}</td>
<td>${Object.entries(r.checks).map(([k,v])=>`<span class=tag>${e(k)} ${v}</span>`).join("")}</td>
<td>${r.fails.map(x=>`<div class=f>${e(x)}</div>`).join("")}${r.warns.map(x=>`<div class=w>${e(x)}</div>`).join("")}</td>
<td class=s>${r.tags.map(t=>`<span class=tag>${e(t)}</span>`).join("")}<br>${r.reasons.map(e).join("<br>")}</td></tr>`).join("")}
[fs,fb,fa].forEach(x=>x.onchange=draw);fq.oninput=draw;draw();
</script></html>"""


def write(cfg, m):
    rep = Path(m["dirs"]["report"])
    rep.mkdir(parents=True, exist_ok=True)
    rows = sorted((_row(e) for e in m["entries"]), key=lambda r: (not r["anomaly"], r["id"]))
    s = summary(m)
    chips = [f"<span><b>{s['total']}</b> 个文件</span>"]
    chips += [f"<span>{BUCKET_LABEL[b]}：<b>{n}</b></span>" for b, n in s["by_bucket"].items() if n]
    chips += [f"<span>通过 <b>{s['passed']}</b>（含提醒 {s['warn']}）</span>",
              f"<span>{s['before_mb']} → {s['after_mb']} MB，节省 <b>{s['saved_mb']} MB（{s['saved_pct']}%）</b></span>"]
    bad = sum(1 for r in rows if r["anomaly"])
    if bad:
        chips.append(f"<span class=f>异常 <b>{bad}</b></span>")
    if s["trashed"]:
        chips.append(f"<span>原片已清理 <b>{s['trashed']}</b></span>")
    page = (HTML.replace("__DATA__", json.dumps(rows, ensure_ascii=False).replace("</", "<\\/"))
            .replace("__SUM__", "".join(chips)).replace("__LINE__", html.escape(LINE_LABEL[m["line"]]))
            .replace("__TIME__", datetime.now().strftime("%Y-%m-%d %H:%M")))
    hp = rep / "report.html"
    hp.write_text(page, encoding="utf-8")
    cp = rep / "report.csv"
    with open(cp, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["#", "文件", "分类", "子组", "状态", "异常", "编码", "分辨率", "原MB", "新MB", "比例", "未通过", "提醒", "原文件", "输出"])
        for r in rows:
            w.writerow([r["id"], r["name"], r["bucket"], r["subgroup"], r["state"], "是" if r["anomaly"] else "",
                        r["codec"], r["res"], r["before_mb"], r["after_mb"], r["ratio"],
                        " | ".join(r["fails"]), " | ".join(r["warns"]), r["src"], r["out"]])
    return {"html": str(hp), "csv": str(cp)}
