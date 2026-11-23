#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_film.py — 把 plan.json 生成成 OpenFilm 工程（每集一个 film.html）

用法：
  python build_film.py --film film.json --plan plan.json --assets ../assets \
         --out episodes --w 1080 --h 1920 --key "绝版,滚出去,我都是为了你好"

产出：
  episodes/ep01/film.html      剪辑（OpenFilm 协议 0.1）
  episodes/ep01/subs/zh.vtt    字幕
  episodes/cues.md             每集素材/时间码/音效点位清单（给渲染和验收用）
  episodes/index.md            总览

说明：
  · 画面：每条分镜一段 <video src="../assets/01.mp4#t=0,15">
  · 字幕：caption 轨道 + WebVTT，关键词用 <c.k> 标黄
  · 声音：如果给了 --cues cues.json 就生成 <audio>；否则在 film.html 里留注释清单
"""
import argparse, json, os, re

def tc(t):
    m, s = divmod(round(t, 3), 60)
    return "%02d:%06.3f" % (int(m), s)

def clean_dlg(dlg):
    """'周屿（画内说话）：搞定！' → '搞定！'"""
    if not dlg or "无对白" in dlg:
        return ""
    d = re.sub(r"（[^）]*）", "", dlg)
    if "：" in d:
        d = d.split("：")[-1]
    elif ":" in d:
        d = d.split(":")[-1]
    return d.strip()

def vtt_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def highlight(text, keys):
    out = vtt_escape(text)
    for k in keys:
        if k and k in out:
            out = out.replace(k, "<c.k>%s</c>" % k)
    return out

def build_vtt(cues, keys):
    head = [
        "WEBVTT", "",
        "STYLE",
        "::cue {",
        '  font-family: "Noto Sans SC", "Microsoft YaHei", sans-serif;',
        "  font-weight: 700; color: #fff; background: transparent;",
        "  text-shadow: 2px 2px 0 #000, -2px 2px 0 #000, 2px -2px 0 #000, -2px -2px 0 #000, 0 0 6px rgba(0,0,0,.55);",
        "}",
        "::cue(.k) { color: #FFD400; }",
        "",
        "NOTE Each cue is one subtitle, as cut by hand in OpenFilm Studio.",
        "",
    ]
    body = []
    for i, c in enumerate(cues, 1):
        body += [str(i),
                 "%s --> %s line:82%% position:50%% size:86%% align:center" % (c["start"], c["end"]),
                 highlight(c["text"], keys),
                 ""]
    return "\n".join(head + body)

def assign_tracks(clips):
    """互不重叠的音频片分到同一条轨道；重叠的另起一条"""
    tracks = []
    for c in clips:
        placed = False
        for tr in tracks:
            if all(c["at"] >= x["end"] or c["end"] <= x["at"] for x in tr):
                tr.append(c)
                placed = True
                break
        if not placed:
            tracks.append([c])
    return tracks

def film_html(ep, film, args, cues):
    rows = []
    t = 0.0
    for segno in ep["segs"]:
        src = args.assets_rel.replace("\\", "/") + "/" + args.asset_pattern.format(no=segno)
        dur = film["meta"]["seg_seconds"]
        rows.append(
            '    <video id="v%03d" src="%s#t=0,%g" at="%g" volume="1"\n'
            '           style="left:0;top:0;width:%dpx;height:%dpx;animation:push %gs linear both"></video>'
            % (segno, src, dur, t, args.w, args.h, dur))
        t += dur

    audio_secs = []
    if cues:
        clips = []
        for c in cues.get("episodes", {}).get(str(ep["no"]), []):
            clips.append(c)
        tracks = assign_tracks(clips)
        for tr in tracks:
            lines = ["  <section>"]
            for c in tr:
                fade = c.get("fade")
                ov = ' overrides=\'[{"fade":[%g,%g]}]\'' % tuple(fade) if fade else ""
                lines.append('    <audio src="%s#t=%g,%g" at="%g" volume="%g"%s></audio>'
                             % (c["src"], c.get("in", 0), c.get("in", 0) + (c["end"] - c["at"]),
                                c["at"], c["volume"], ov))
            lines.append("  </section>")
            audio_secs.append("\n".join(lines))
    else:
        audio_secs.append(
            "  <!-- 音频待补：BGM 建议「%s」；音效 %s。\n"
            "       放好文件后在下面加 <section><audio src=\"../assets/xxx.mp3#t=0,N\" at=\"T\" volume=\"V\"></audio></section> -->"
            % (ep["bgm"], "、".join(n for n, _ in ep["sfx"]) or "无"))

    return """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=%d, height=%d">
<title>%s · 第%d集</title>
<style>
  video { object-fit: cover; object-position: center 30%%; }
  @keyframes push { from { scale: 1 } to { scale: 1.03 } }
</style>
</head>
<body>
  <!-- 轨道1 字幕（放最前，最上层） -->
  <section><track kind="captions" src="subs/zh.vtt" srclang="zh" label="中文"></section>
  <!-- 轨道2 画面 -->
  <section>
%s
  </section>
  <!-- 轨道3+ 声音 -->
%s
</body>
</html>
""" % (args.w, args.h, args.title or "短剧", ep["no"], "\n".join(rows), "\n".join(audio_secs))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--film", default="film.json")
    ap.add_argument("--plan", default="plan.json")
    ap.add_argument("--assets", default="../assets", help="素材目录（写进 film.html 的相对路径）")
    ap.add_argument("--assets-rel", default="../assets", help=argparse.SUPPRESS)
    ap.add_argument("--asset-pattern", default="{no:02d}.mp4", help="素材命名规则，如 {no:02d}.mp4 或 seg-{no}.mp4")
    ap.add_argument("--out", default="episodes")
    ap.add_argument("--w", type=int, default=1080)
    ap.add_argument("--h", type=int, default=1920)
    ap.add_argument("--title", default="")
    ap.add_argument("--key", default="", help="要标黄的词，逗号分隔")
    ap.add_argument("--cues", default="", help="可选：cues.json（每集的 BGM/音效文件）")
    ap.add_argument("--limit", type=int, default=0, help="只生成前 N 集（试剪用）")
    a = ap.parse_args()
    a.assets_rel = a.assets
    keys = [k.strip() for k in a.key.split(",") if k.strip()]

    film = json.load(open(a.film, encoding="utf-8"))
    plan = json.load(open(a.plan, encoding="utf-8"))
    cues = json.load(open(a.cues, encoding="utf-8")) if a.cues else None
    seg_map = {s["no"]: s for s in film["segments"]}
    seg_s = film["meta"]["seg_seconds"]

    os.makedirs(a.out, exist_ok=True)
    index = ["# 分集工程", "", "| 集 | 时长 | 分镜段 | 工程 |", "|---|---|---|---|"]
    cue_md = ["# 剪辑点位清单", ""]

    eps = plan["episodes"]
    if a.limit:
        eps = eps[:a.limit]

    for ep in eps:
        d = os.path.join(a.out, "ep%02d" % ep["no"])
        os.makedirs(os.path.join(d, "subs"), exist_ok=True)

        # 字幕：每镜一条（只给有台词的镜头）
        cues_list, t0 = [], 0.0
        for segno in ep["segs"]:
            seg = seg_map[segno]
            n = max(1, len(seg["shots"]))
            step = seg_s / n
            for k, sh in enumerate(seg["shots"]):
                txt = clean_dlg(sh["dlg"])
                if txt:
                    cues_list.append({"start": tc(t0 + k * step), "end": tc(t0 + (k + 1) * step), "text": txt})
            t0 += seg_s

        open(os.path.join(d, "subs", "zh.vtt"), "w", encoding="utf-8").write(build_vtt(cues_list, keys))
        open(os.path.join(d, "film.html"), "w", encoding="utf-8").write(film_html(ep, film, a, cues))

        index.append("| %d | %.0fs | %s | `%s/film.html` |"
                     % (ep["no"], ep["duration"], ",".join(map(str, ep["segs"])), os.path.basename(d)))
        cue_md.append("## 第%d集（%.0fs）" % (ep["no"], ep["duration"]))
        cue_md.append("")
        cue_md.append("| 时间码 | 分镜段 | 素材 | 场景 | 卡点 |")
        cue_md.append("|---|---|---|---|---|")
        tt = 0.0
        for segno in ep["segs"]:
            seg = seg_map[segno]
            cue_md.append("| %s | %d | `%s` | %s | %s |"
                          % (tc(tt), segno, a.asset_pattern.format(no=segno), seg["scene"],
                             seg["end"][:40]))
            tt += seg_s
        cue_md.append("")
        cue_md.append("BGM：%s" % ep["bgm"])
        cue_md.append("")
        cue_md.append("音效：%s" % ("；".join("%s（%ddB）" % (n, v) for n, v in ep["sfx"]) or "无"))
        cue_md.append("")
        cue_md.append("字幕：%d 条" % len(cues_list))
        cue_md.append("")

    open(os.path.join(a.out, "index.md"), "w", encoding="utf-8").write("\n".join(index))
    open(os.path.join(a.out, "cues.md"), "w", encoding="utf-8").write("\n".join(cue_md))
    print("已生成 %d 集 → %s" % (len(eps), os.path.abspath(a.out)))
    print("工程：%s/ep01/film.html" % a.out)
    print("清单：%s/cues.md" % a.out)

if __name__ == "__main__":
    main()
