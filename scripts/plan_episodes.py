#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plan_episodes.py — 把 film.json 切成短剧分集，并生成剪辑工单

用法：
  python plan_episodes.py --film film.json --target 75 --title "剧名" --out plan

产出：
  plan.json        机器可读分集（段序、时长、入出点、钩子）
  分集工单.csv     给 OpenFilm / 剪映智能体读的工单
  分集表.xlsx      给人看的表（集/时长/分镜段/剧情/卡点/情绪/BGM/音效）

分集逻辑：
  1) 去掉完全重复段（--drop-near 可连"疑似重述"一起去掉）
  2) 目标时长 → 理想段数；每集在 [min,max] 段内取最接近理想的长度
  3) 同样接近时，优先切在"换场景"的位置（天然分集点）
  4) 集末钩子 = 该段最后一镜的对白；没有对白则用结束状态
"""
import argparse, csv, json, os, re
from collections import OrderedDict

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    openpyxl = None

# 情绪启发式：命中关键词 → 情绪档
EMOTION_RULES = [
    ("冲突", ["吵", "骂", "抢", "扔", "砸", "推", "指着", "打翻", "摔", "动手", "吼"]),
    ("危机", ["危机", "泄露", "取消资格", "组委会", "裂痕", "抄袭", "举报", "威胁", "行贿", "毁掉"]),
    ("泪点", ["哭", "流泪", "泪", "对不起", "滚出去", "日记", "遗嘱", "去世", "哽咽"]),
    ("爽点", ["颁奖", "冠军", "翻盘", "击掌", "反击", "揭穿", "报警", "大奖", "中奖"]),
    ("笑点", ["笑", "荒诞", "风水", "保鲜膜", "核桃", "牙签", "表情包", "指甲油", "群聊"]),
    ("温情", ["拥抱", "理解", "名字", "陪你", "谢谢", "回家", "擦灰", "并肩"]),
]

# 情绪 → BGM 建议（只写可商用来源，不写有版权的热门歌）
BGM_BY_EMOTION = OrderedDict([
    ("冲突", "紧张低频 pulse（Pixabay: tension pulse）/ 剪映商用专区「悬疑 压迫」"),
    ("危机", "压迫旋律（Pixabay: suspense drone）/ 剪映商用专区「紧张」"),
    ("笑点", "喜剧拨弦（Pixabay: funny quirky）/ 剪映商用专区「搞怪」"),
    ("泪点", "钢琴＋弦乐（Pixabay: sad piano cinematic）/ 剪映商用专区「亲情 伤感」"),
    ("爽点", "史诗/励志（Pixabay: epic cinematic）/ 剪映商用专区「燃 卡点」"),
    ("温情", "温暖钢琴（Pixabay: warm piano）/ 剪映商用专区「治愈 亲情」"),
    ("日常", "轻快 ukulele / 木吉他（Pixabay: happy ukulele）"),
])

# 音效关键词 → 音效名与建议音量
SFX_RULES = [
    (["门铃"], "门铃（普通/急促）", -12),
    (["防盗门", "摔门", "关门"], "关门/摔门", -10),
    (["手机", "消息", "群"], "手机消息连震", -16),
    (["电话", "组委会", "来电"], "电话铃声", -14),
    (["垃圾", "塑料袋", "袋子"], "塑料袋/垃圾袋", -18),
    (["垃圾桶", "扔进"], "垃圾桶哐当", -12),
    (["抹布", "擦", "滴水"], "抹布拧水/擦拭", -16),
    (["掸子", "抽打"], "鸡毛掸子抽打", -10),
    (["气吹", "软毛刷", "保养"], "气吹/软毛刷", -24),
    (["锁", "撬", "日记"], "发夹撬锁/锁芯", -14),
    (["翻", "纸", "画稿", "相册"], "纸页翻动", -20),
    (["胶水", "喷漆", "失灵"], "胶水/喷漆", -18),
    (["镊子", "零件", "模型"], "镊子/零件轻放", -22),
    (["探针", "裂痕"], "探针轻碰（高频叮）", -12),
    (["金缮", "金线"], "金缮落笔", -18),
    (["收音机", "半导体"], "收音机调频", -18),
    (["掌", "颁奖", "领奖"], "掌声（稀→雷动）", -14),
    (["心跳", "深夜", "睁眼"], "心跳/耳鸣", -20),
]

def emotion_of(text):
    best, score = "日常", 0
    for name, kws in EMOTION_RULES:
        s = sum(text.count(k) for k in kws)
        if s > score:
            best, score = name, s
    return best

def sfx_of(text, limit=4):
    out = []
    for kws, name, vol in SFX_RULES:
        if any(k in text for k in kws) and name not in [x[0] for x in out]:
            out.append((name, vol))
        if len(out) >= limit:
            break
    return out

def seg_text(seg):
    return " ".join(sh["pic"] + sh["dlg"] for sh in seg["shots"]) + " " + seg.get("end", "")

def hook_of(seg):
    for sh in reversed(seg["shots"]):
        if sh["dlg"] and "无对白" not in sh["dlg"]:
            return re.sub(r"（[^）]*）", "", sh["dlg"]).strip()
    return seg.get("end", "")

def plan(film, target=75.0, min_seg=4, max_seg=8, drop_near=False, order=None):
    seg_s = film["meta"]["seg_seconds"]
    drop = set(film["dupes"])
    if drop_near:
        drop |= set(x[0] for x in film["near"])
    usable = [s for s in film["segments"] if s["no"] not in drop]
    if order:
        by_no = {s["no"]: s for s in usable}
        seq = [by_no[n] for n in order if n in by_no]
        # 补上 order 里没提到的段（放在末尾，保持不丢素材）
        have = set(order)
        seq += [s for s in usable if s["no"] not in have]
        usable = seq
    ideal = max(min_seg, min(max_seg, round(target / seg_s)))

    eps, i = [], 0
    while i < len(usable):
        left = len(usable) - i
        if left <= max_seg:
            pick = left
        else:
            best, best_key = ideal, None
            for size in range(min_seg, max_seg + 1):
                if size > left:
                    continue
                nxt = usable[i + size] if i + size < len(usable) else None
                scene_change = 1 if (nxt and nxt["scene"] != usable[i + size - 1]["scene"]) else 0
                # 越小越好；同样接近时优先换场景
                key = (abs(size - ideal), -scene_change)
                if best_key is None or key < best_key:
                    best, best_key = size, key
            pick = best
        chunk = usable[i:i + pick]
        i += pick
        eps.append(chunk)

    out = []
    t = 0.0
    for n, chunk in enumerate(eps, 1):
        dur = len(chunk) * seg_s
        text = " ".join(seg_text(s) for s in chunk)
        emo = emotion_of(text)
        out.append({
            "no": n,
            "segs": [s["no"] for s in chunk],
            "count": len(chunk),
            "in": round(t, 3),
            "out": round(t + dur, 3),
            "duration": dur,
            "scene": "/".join(dict.fromkeys([s["scene"] for s in chunk if s["scene"]])),
            "plot": (chunk[0]["shots"][0]["pic"] if chunk[0]["shots"] else "")[:80],
            "hook": hook_of(chunk[-1]),
            "emotion": emo,
            "bgm": BGM_BY_EMOTION.get(emo, BGM_BY_EMOTION["日常"]),
            "sfx": sfx_of(text),
        })
        t += dur
    return out, {"episodes": len(out), "seconds": t, "dropped": len(drop), "usable": len(usable)}

def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["集", "入点", "出点", "时长", "段数", "分镜段(按顺序)", "场景",
                    "开场画面", "集末卡点", "情绪", "BGM建议", "音效建议"])
        for r in rows:
            def tc(x):
                m, s = divmod(round(x, 2), 60)
                return "%d:%05.2f" % (m, s)
            w.writerow([r["no"], tc(r["in"]), tc(r["out"]), "%.0fs" % r["duration"], r["count"],
                        ",".join(map(str, r["segs"])), r["scene"], r["plot"], r["hook"],
                        r["emotion"], r["bgm"],
                        "；".join("%s(%ddB)" % (n, v) for n, v in r["sfx"])])

def write_xlsx(rows, path, title=""):
    if openpyxl is None:
        return
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "分集表"
    ws.sheet_view.showGridLines = False
    hs = ["集", "时长", "分镜段（顺序）", "场景", "开场画面", "集末卡点", "情绪", "BGM 建议", "音效建议"]
    wd = [5, 7, 26, 16, 40, 44, 7, 38, 34]
    TH = Side(style="thin", color="BFBFBF")
    BD = Border(left=TH, right=TH, top=TH, bottom=TH)
    for i, (h, w) in enumerate(zip(hs, wd), 1):
        c = ws.cell(row=1, column=i, value=h)
        c.font = Font(bold=True, color="FFFFFF", size=10)
        c.fill = PatternFill("solid", fgColor="1F4E79")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = BD
        ws.column_dimensions[get_column_letter(i)].width = w
    for r, row in enumerate(rows, 2):
        vals = [row["no"], "%.0fs" % row["duration"], ",".join(map(str, row["segs"])),
                row["scene"], row["plot"], row["hook"], row["emotion"], row["bgm"],
                "；".join("%s(%ddB)" % (n, v) for n, v in row["sfx"])]
        for c, v in enumerate(vals, 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.border = BD
            cell.font = Font(size=9)
            cell.alignment = Alignment(vertical="top", wrap_text=True,
                                       horizontal="center" if c in (1, 2, 7) else "left")
        ws.row_dimensions[r].height = 46
    ws.freeze_panes = "A2"
    if title:
        wb.properties.title = title
    wb.save(path)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--film", default="film.json")
    ap.add_argument("--target", type=float, default=75.0, help="单集目标秒数：60/75/90")
    ap.add_argument("--min-seg", type=int, default=4)
    ap.add_argument("--max-seg", type=int, default=8)
    ap.add_argument("--drop-near", action="store_true", help="连疑似重述段一起去掉")
    ap.add_argument("--order", default="", help="可选：按 order.json 里的段号顺序播放（[1,2,3,7,4,...]）")
    ap.add_argument("--title", default="")
    ap.add_argument("--out", default="plan")
    a = ap.parse_args()

    film = json.load(open(a.film, encoding="utf-8"))
    order = json.load(open(a.order, encoding="utf-8")) if a.order else None
    if isinstance(order, dict):
        order = order.get("order")
    rows, meta = plan(film, a.target, a.min_seg, a.max_seg, a.drop_near, order)
    base = a.out
    json.dump({"meta": meta, "episodes": rows}, open(base + ".json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    write_csv(rows, base + "-工单.csv")
    write_xlsx(rows, base + "-分集表.xlsx", a.title)

    print("集数 %d ｜ 总长 %.1f 分钟 ｜ 可用 %d 段 ｜ 去掉 %d 段"
          % (meta["episodes"], meta["seconds"] / 60, meta["usable"], meta["dropped"]))
    sizes = {}
    for r in rows:
        sizes[r["count"]] = sizes.get(r["count"], 0) + 1
    print("每集段数分布：", ", ".join("%d段×%d集" % (k, v) for k, v in sorted(sizes.items())))
    print("产出：%s.json / %s-工单.csv / %s-分集表.xlsx" % (base, base, base))

if __name__ == "__main__":
    main()
