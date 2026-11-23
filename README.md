# 短剧自动剪辑 · Short Drama Auto Cut

把 **剧本 + 分镜表** 变成 **能渲染的成片工程**。
一条流水线跑完：解析 → 查重 → 分集 → 字幕 → 音效/BGM 点位 → OpenFilm 工程 → 自检。

面向抖音 / 红果竖屏短剧，尤其适合"每段 15 秒的 AI 生成素材"。

```
剧本.docx + 分镜.xlsx
      ↓ parse_storyboard.py   解析 + 查重（出体检报告）
   film.json
      ↓ plan_episodes.py      按平台节奏分集（出分集表 + 工单）
   plan.json / 分集工单.csv / 分集表.xlsx
      ↓ build_film.py         生成 OpenFilm 工程（film.html + WebVTT）
   episodes/ep01/… / cues.md
      ↓ check_film.py         渲染前自检
   OK → 丢进 OpenFilm Studio 导出
```

## 安装

放到 DSH 的 skills 目录即可（DSH 会自动加载）：

```bash
git clone https://github.com/3382436049-afk/short-drama-auto-cut.git \
  ~/.dsh/skills/short-drama-auto-cut
```

Windows：

```powershell
git clone https://github.com/3382436049-afk/short-drama-auto-cut.git "$env:USERPROFILE\.dsh\skills\short-drama-auto-cut"
```

依赖：Python 3.9+、`openpyxl`（读分镜 xlsx）、`python-docx`（读剧本）。

```bash
pip install openpyxl python-docx
```

## 快速开始

```bash
S=~/.dsh/skills/short-drama-auto-cut/scripts

# 1) 解析分镜与剧本，顺手做体检（重复段、时长）
python $S/parse_storyboard.py \
    --storyboard 分镜.xlsx --script 剧本.docx --seg 15 \
    --out film.json --report 体检报告.md

# 2) 分集：60 / 75 / 90 秒一集
python $S/plan_episodes.py --film film.json --target 75 --title "剧名" --out plan

# 3) 生成工程（先只做第 1 集试剪）
python $S/build_film.py --film film.json --plan plan.json \
    --out episodes --key "绝版,滚出去" --limit 1

# 4) 自检
python $S/check_film.py --path episodes
```

素材按分镜号命名（`01.mp4`、`02.mp4`…），放在 `episodes/../assets/`；命名不同就加
`--asset-pattern "seg-{no}.mp4"`。

## 目录

```
SKILL.md                  技能主文档（决策规则 + 验收清单）
scripts/
  parse_storyboard.py     解析分镜 xlsx / 剧本 docx，查重
  plan_episodes.py        分集、钩子、情绪→BGM/音效建议
  build_film.py           生成 OpenFilm film.html + subs/zh.vtt
  check_film.py           渲染前自检（协议/时长/重叠/素材存在）
references/
  style-guide.md          抖音·红果节奏与字幕规范
  music-licensing.md      可商用配乐与授权
  sfx-library.md          音效字典（动作→dB→搜索词）
  film-html.md            OpenFilm 协议速查
```

## 它替代了哪些"手艺"

- **查重**：AI 分镜里常有 10%–15% 的重复/重述镜头，直接拼会"卡带"。脚本按相似度（≥0.85，或相邻 4 段内 ≥0.6）自动删。
- **分集**：按目标秒数切，切点优先落在换场景处，集末钩子取对白半句。
- **字幕**：只给有台词的镜头，白字黑描边、`line:82%`、关键词标黄。
- **声音**：音效绑动作（-10~-14dB），配乐只用可商用来源，并强制"抖音三招"（抽帧静音 / Drop 重音 / 集尾空拍）。

## 输出

- `film.html`：OpenFilm 协议 0.1 的剪辑文件，1080×1920 竖屏，字幕走 caption 轨道
- `subs/zh.vtt`：WebVTT 字幕（含 `::cue` 样式与关键词高亮）
- `cues.md`：每集时间码、素材、卡点、音效点位，给人工核对
- `分集表.xlsx` / 分集工单.csv：给剪辑与智能体读

## License

MIT。见 [LICENSE](LICENSE)。
