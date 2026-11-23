#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_pipeline.py — 端到端冒烟测试（CI 用，也可本地跑）

用一份合成的 6 段分镜跑完 parse → plan → build → check，
断言产物存在且自检通过。不依赖任何真实素材。

    python tests/test_pipeline.py
"""
import os, shutil, subprocess, sys, tempfile
import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")

def make_storyboard(path, n_seg=6):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "分镜"
    ws.append(["序号", "剧本", "出场人物", "场景", "道具"])
    for i in range(1, n_seg + 1):
        shots = []
        for k in range(1, 6):
            dlg = ("甲（画内说话）：这是第%d段的第%d句话。" % (i, k)) if k % 2 == 0 else "（无对白）"
            shots.append("镜号%d：【中景】【正面机位】【固定镜头】画面：第%d段第%d镜的画面。；对白：%s"
                         % (k, i, k, dlg))
        body = ("小节%d：\n场景：客厅\n人物：甲、乙\n" % i) + "\n".join(shots) + \
               "\n结束状态：第%d段结束。" % i
        ws.append(["分镜 %d" % i, body, "甲、乙", "客厅", "手机"])
    wb.save(path)

def run(args, expect=0):
    r = subprocess.run([sys.executable] + args, capture_output=True, text=True)
    if r.returncode != expect:
        print(r.stdout)
        print(r.stderr)
        raise SystemExit("FAILED: %s (exit %d)" % (" ".join(args), r.returncode))
    return r.stdout

def main():
    tmp = os.path.join(ROOT, "tests", ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    try:
        sb = os.path.join(tmp, "分镜.xlsx")
        make_storyboard(sb)

        run([os.path.join(SCRIPTS, "parse_storyboard.py"),
             "--storyboard", sb, "--out", os.path.join(tmp, "film.json")])

        run([os.path.join(SCRIPTS, "plan_episodes.py"),
             "--film", os.path.join(tmp, "film.json"), "--target", "45",
             "--out", os.path.join(tmp, "plan")])

        run([os.path.join(SCRIPTS, "build_film.py"),
             "--film", os.path.join(tmp, "film.json"),
             "--plan", os.path.join(tmp, "plan.json"),
             "--out", os.path.join(tmp, "episodes"), "--limit", "1"])

        html = os.path.join(tmp, "episodes", "ep01", "film.html")
        vtt = os.path.join(tmp, "episodes", "ep01", "subs", "zh.vtt")
        assert os.path.exists(html), "film.html 没生成"
        assert os.path.exists(vtt), "字幕没生成"
        assert "WEBVTT" in open(vtt, encoding="utf-8").read(), "VTT 格式不对"
        assert "kind=\"captions\"" in open(html, encoding="utf-8").read(), "缺少字幕轨"

        # 自检必须通过（无 ERROR）
        out = run([os.path.join(SCRIPTS, "check_film.py"),
                   "--path", os.path.join(tmp, "episodes")])
        assert "0 个有错误" in out, "自检未通过：\n" + out

    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("PASS: 端到端冒烟测试通过")

if __name__ == "__main__":
    main()
