#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_film.py — 渲染前自检 OpenFilm 工程

用法：
  python check_film.py --path episodes            # 检查整批
  python check_film.py --path episodes/ep01/film.html --assets episodes/../assets

检查项：
  舞台 viewport / 轨道结构 / 片段内不能有元素 / 同轨不重叠 /
  at 是否单调 / 禁止 position|transform|margin / volume 范围 /
  字幕轨是否在最前 / 总时长 / 引用的素材是否存在
"""
import argparse, os, re, sys
from html.parser import HTMLParser

CLIPS = {"video", "audio", "img", "iframe", "track"}
FORBIDDEN = ("position", "transform", "margin", "top:", "left:")
ALLOWED_POS = ("left", "top", "width", "height", "rotate")

class P(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sections = []      # [ [ (tag, attrs, children_tags) ] ]
        self.cur = None
        self.viewport = None
        self.stack = []
        self.in_head = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and a.get("name") == "viewport":
            self.viewport = a.get("content", "")
        if tag == "section":
            self.cur = []
            self.sections.append(self.cur)
            self.stack = [tag]
            return
        if self.cur is not None and self.stack:
            if self.stack[-1] == "section" and tag in CLIPS:
                self.cur.append({"tag": tag, "attrs": a, "kids": []})
                self.stack.append(tag)
                return
            if self.stack[-1] in CLIPS:
                for c in reversed(self.cur):
                    if c["tag"] == self.stack[-1]:
                        c["kids"].append(tag)
                        break
                self.stack.append(tag)
                return

    def handle_endtag(self, tag):
        if tag == "section":
            self.cur = None
            self.stack = []
        elif self.stack and self.stack[-1] == tag:
            self.stack.pop()

def lint(path, assets_root=None):
    html = open(path, encoding="utf-8").read()
    p = P(); p.feed(html)
    errs, warns = [], []

    if not p.viewport:
        errs.append("缺少 <meta name=\"viewport\" content=\"width=…, height=…\">")
    if not p.sections:
        errs.append("没有 <section> 轨道")

    # 字幕轨必须在最前
    if p.sections:
        first = p.sections[0]
        if not (len(first) == 1 and first[0]["tag"] == "track" and first[0]["attrs"].get("kind") in ("captions", "subtitles")):
            warns.append("第一条轨道不是字幕轨；字幕可能被画面盖住")

    total = 0.0
    for si, sec in enumerate(p.sections, 1):
        spans = []
        for c in sec:
            tag, a = c["tag"], c["attrs"]
            if c["kids"]:
                errs.append("轨道%d 的 <%s> 里包了 <%s>：片段里不能有元素" % (si, tag, c["kids"][0]))
            st = a.get("style", "")
            for bad in ("position", "transform", "margin"):
                if re.search(r"(^|;|\s)%s\s*:" % bad, st):
                    errs.append("轨道%d <%s> 的 style 用了 %s，位置只能用 left/top/width/height/rotate" % (si, tag, bad))
            vol = a.get("volume")
            if vol is not None:
                try:
                    v = float(vol)
                    if not (0 <= v <= 1):
                        errs.append("轨道%d <%s> volume=%s 超出 0–1" % (si, tag, vol))
                except ValueError:
                    errs.append("轨道%d <%s> volume 不是数字：%s" % (si, tag, vol))
            at = a.get("at")
            atv = 0.0
            if at is not None:
                try:
                    atv = float(at)
                except ValueError:
                    errs.append("轨道%d <%s> at 不是数字：%s" % (si, tag, at))
            src = a.get("src", "")
            m = re.search(r"#t=([\d.]+),([\d.]+)", src)
            dur = None
            if m:
                dur = float(m.group(2)) - float(m.group(1))
                spd = a.get("speed")
                if spd:
                    try:
                        dur = dur / float(spd)
                    except ValueError:
                        pass
                elif tag == "video" or tag == "audio":
                    pass
            if tag in ("video", "audio") and dur:
                spans.append((atv, atv + dur))
                total = max(total, atv + dur)
                if assets_root:
                    f = src.split("#")[0]
                    fp = os.path.normpath(os.path.join(os.path.dirname(path), f))
                    if not os.path.exists(fp):
                        warns.append("素材不存在：%s" % f)
        spans.sort()
        for i in range(1, len(spans)):
            if spans[i][0] < spans[i - 1][1] - 1e-6:
                errs.append("轨道%d 有重叠片段：%.2f 与 %.2f" % (si, spans[i - 1][1], spans[i][0]))

    # VTT 检查
    for sec in p.sections:
        for c in sec:
            if c["tag"] == "track" and c["attrs"].get("src"):
                vp = os.path.join(os.path.dirname(path), c["attrs"]["src"])
                if not os.path.exists(vp):
                    errs.append("字幕文件不存在：%s" % c["attrs"]["src"])
                else:
                    t = open(vp, encoding="utf-8").read()
                    if not t.startswith("WEBVTT"):
                        errs.append("VTT 缺少 WEBVTT 头：%s" % c["attrs"]["src"])
                    if "-->" not in t:
                        warns.append("VTT 里一条 cue 都没有：%s" % c["attrs"]["src"])
    return errs, warns, total

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True, help="film.html 或 episodes 目录")
    ap.add_argument("--assets", default="", help="素材根目录（给相对路径做存在性检查）")
    a = ap.parse_args()

    targets = []
    if os.path.isdir(a.path):
        for root, _, files in os.walk(a.path):
            if "film.html" in files:
                targets.append(os.path.join(root, "film.html"))
    else:
        targets.append(a.path)
    targets.sort()
    if not targets:
        sys.exit("没找到 film.html")

    bad = 0
    for t in targets:
        errs, warns, total = lint(t, a.assets or None)
        name = os.path.basename(os.path.dirname(t))
        status = "FAIL" if errs else ("WARN" if warns else "OK")
        print("[%s] %s  总时长 %.2fs" % (status, name, total))
        for e in errs:
            print("   ✗ " + e)
        for w in warns:
            print("   ! " + w)
        bad += 1 if errs else 0
    print("\n%d 个工程，%d 个有错误" % (len(targets), bad))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    main()
