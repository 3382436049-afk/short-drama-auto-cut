#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_storyboard.py — 把分镜表(xlsx)与剧本(docx)解析成统一的 film.json

用法：
  python parse_storyboard.py --storyboard 分镜.xlsx [--script 剧本.docx] [--seg 15] --out film.json
  python parse_storyboard.py --storyboard 分镜.xlsx --report report.md

输出 film.json：
{
  "meta": {"seg_seconds":15, "segments":300, "total_seconds":4500, "unique_seconds":3945},
  "segments": [{"no":1,"scene":"...","chars":"...","props":"...","end":"...",
                "shots":[{"i":1,"size":"中景","cam":"正面机位","move":"固定镜头","pic":"...","dlg":"..."}]}],
  "dupes": [8,42],        # 与前面某段几乎完全一致，建议删
  "near":  [7,18],        # 疑似同一动作重述（0.6~0.85），需人工判断
  "episodes": [{"no":1,"heading":"...","chars":817,"scenes":[{"no":"1-1","text":"..."}],"lines":[...]}]
}
"""
import argparse, json, re, sys
from difflib import SequenceMatcher

try:
    import openpyxl
except ImportError:
    openpyxl = None
try:
    import docx
except ImportError:
    docx = None


def norm(s):
    s = re.sub(r"【[^】]*】|镜号\d+：|画面：|对白：|（[^）]*）|小节\d+：|结束状态：", "", s or "")
    return re.sub(r"\s+", "", s)


def parse_storyboard(path):
    """分镜表：优先找含 '镜号' 的工作表，按 '序号' 排序。"""
    if openpyxl is None:
        sys.exit("需要 openpyxl：pip install openpyxl")
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = None
    for name in wb.sheetnames:
        cand = wb[name]
        header = [str(c.value or "") for c in next(cand.iter_rows(min_row=1, max_row=1))]
        if any("序号" in h for h in header):
            ws = cand
            break
        # 无表头时按内容判断
        for r in cand.iter_rows(min_row=1, max_row=3, values_only=True):
            if r and isinstance(r[0], str) and "分镜" in r[0]:
                ws = cand
                break
        if ws:
            break
    if ws is None:
        sys.exit("没找到分镜工作表（需要含“序号”或“分镜 N”的列）")

    rows = list(ws.iter_rows(min_row=1, values_only=True))
    header = [str(c or "") for c in rows[0]]
    def col(*names):
        for i, h in enumerate(header):
            for n in names:
                if n in h:
                    return i
        return None
    c_no, c_body = col("序号", "分镜"), col("剧本", "内容", "画面")
    c_chars, c_scene, c_props = col("人物"), col("场景"), col("道具")
    if c_body is None:
        sys.exit("分镜表里找不到“剧本/内容”列")

    segs = []
    for r in rows[1:]:
        if r is None or len(r) <= c_body:
            continue
        raw_no = r[c_no] if c_no is not None else None
        if raw_no is None:
            continue
        m = re.search(r"(\d+)", str(raw_no))
        if not m:
            continue
        no = int(m.group(1))
        body = str(r[c_body] or "")
        shots = []
        parts = re.split(r"镜号(\d+)：", body)
        for i in range(1, len(parts), 2):
            idx, txt = int(parts[i]), parts[i + 1]
            tags = re.findall(r"【([^】]*)】", txt)
            mp = re.search(r"画面：(.*?)(?:；|\n)", txt)
            md = re.search(r"对白：([^\n]*)", txt)
            shots.append({
                "i": idx,
                "size": tags[0] if len(tags) > 0 else "",
                "cam": tags[1] if len(tags) > 1 else "",
                "move": tags[2] if len(tags) > 2 else "",
                "pic": (mp.group(1).strip() if mp else ""),
                "dlg": (md.group(1).strip() if md else ""),
            })
        me = re.search(r"结束状态：(.*)", body, re.S)
        segs.append({
            "no": no,
            "scene": str(r[c_scene] or "") if c_scene is not None else "",
            "chars": str(r[c_chars] or "") if c_chars is not None else "",
            "props": str(r[c_props] or "") if c_props is not None else "",
            "end": (me.group(1).strip().replace("\n", " ") if me else ""),
            "shots": shots,
        })
    segs.sort(key=lambda s: s["no"])
    return segs


def detect_dupes(segs, dup_th=0.85, near_th=0.60, window=12):
    """同一段镜号内容在邻近重复出现 → 重复/重述。返回 (dupes, near, pairs)"""
    texts = ["|".join(norm(sh["pic"] + sh["dlg"]) for sh in s["shots"]) for s in segs]
    dupes, near, pairs = [], [], []
    for i in range(len(segs)):
        for j in range(max(0, i - window), i):
            if not texts[i] or not texts[j]:
                continue
            r = SequenceMatcher(None, texts[i], texts[j]).ratio()
            if r >= dup_th or (r >= near_th and (i - j) <= 4):
                dupes.append(segs[i]["no"])
                pairs.append((segs[i]["no"], segs[j]["no"], round(r, 2), "dup"))
                break
            if r >= near_th:
                near.append((segs[i]["no"], segs[j]["no"], round(r, 2), "near"))
    return sorted(set(dupes)), near, pairs


def parse_script(path, seg_seconds=15):
    """剧本：按“第N集”切分，收集场次与台词，用于给分集提钩子。"""
    if docx is None:
        return []
    d = docx.Document(path)
    lines = [p.text.rstrip() for p in d.paragraphs]
    eps, cur = [], None
    for ln in lines:
        m = re.match(r"^第(\d+)集\s*(.*)$", ln.strip())
        if m:
            cur = {"no": int(m.group(1)), "heading": m.group(2), "chars": 0,
                   "scenes": [], "lines": [], "dialogue": []}
            eps.append(cur)
            continue
        if cur is None:
            continue
        t = ln.strip()
        if not t or t.startswith("（第"):
            continue
        cur["chars"] += len(t)
        sm = re.match(r"^(\d+-\d+)[\.．]?\s*(.*)$", t)
        if sm:
            cur["scenes"].append({"no": sm.group(1), "text": sm.group(2)})
            continue
        if t.startswith("△"):
            continue
        cur["lines"].append(t)
        if re.match(r"^[^（].{0,8}[：:]", t):
            cur["dialogue"].append(t)
    return eps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--storyboard", required=True)
    ap.add_argument("--script")
    ap.add_argument("--seg", type=float, default=15.0, help="每段素材秒数（默认15）")
    ap.add_argument("--out", default="film.json")
    ap.add_argument("--report")
    a = ap.parse_args()

    segs = parse_storyboard(a.storyboard)
    dupes, near, pairs = detect_dupes(segs)
    eps = parse_script(a.script, a.seg) if a.script else []

    total = len(segs) * a.seg
    unique = (len(segs) - len(dupes)) * a.seg
    data = {
        "meta": {
            "seg_seconds": a.seg,
            "segments": len(segs),
            "total_seconds": total,
            "dupes": len(dupes),
            "unique_seconds": unique,
            "shots": sum(len(s["shots"]) for s in segs),
        },
        "segments": segs,
        "dupes": dupes,
        "near": [n for n in near],
        "episodes": eps,
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    msg = [
        "# 分镜体检报告",
        "",
        "| 项 | 值 |",
        "|---|---|",
        "| 分镜段 | %d |" % len(segs),
        "| 镜号 | %d |" % data["meta"]["shots"],
        "| 原始时长 | %.1f 分钟 |" % (total / 60),
        "| 完全重复（建议删） | %d 段 / %.1f 分钟 |" % (len(dupes), len(dupes) * a.seg / 60),
        "| 疑似重述（人工判断） | %d 处 |" % len(near),
        "| 可用时长 | %.1f 分钟 |" % (unique / 60),
        "",
        "## 完全重复段",
        ", ".join(map(str, dupes)) or "无",
        "",
        "## 疑似重述（段A ≈ 段B，相似度）",
    ]
    for x in near:
        msg.append("- %d ≈ %d（%.2f）" % (x[0], x[1], x[2]))
    if not near:
        msg.append("无")
    msg += ["", "## 下一步", "把 film.json 交给 plan_episodes.py 分集。"]
    text = "\n".join(msg)
    if a.report:
        open(a.report, "w", encoding="utf-8").write(text)
    print(text)


if __name__ == "__main__":
    main()
