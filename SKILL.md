---
name: short-drama-auto-cut
description: 短剧自动剪辑流水线。给定剧本(docx/txt)与分镜表(xlsx)，自动完成分镜解析、重复素材体检、按平台节奏分集、生成字幕与音效/配乐点位，并输出可渲染的 OpenFilm 工程(film.html + WebVTT)；也可导出剪映执行工单。适用于抖音/红果竖屏短剧、AI 生成素材的批量成片。
version: 1.0.0
metadata:
  requires:
    bins: [python3]
    python: [openpyxl, python-docx]
  outputs: [film.json, plan.json, 分集工单.csv, 分集表.xlsx, episodes/*/film.html, subs/zh.vtt]
---

# 短剧自动剪辑（剧本 + 分镜 → 成片工程）

把"剧本 + 分镜表"变成"能渲染的工程"。四步流水线，每步都有产物可检查，不要跳步。

## 何时用

- 用户给了剧本和分镜表（尤其每段 15 秒的 AI 素材），要剪成竖屏短剧
- 要批量做几十集，需要统一的字幕/音效/配乐规范
- 要 OpenFilm 工程（写 `film.html`）或剪映执行工单

## 输入确认（先问清这四项）

1. **剧本**：docx 或 txt，按"第N集"分集
2. **分镜表**：xlsx，含"序号/剧本/人物/场景"列，正文里有"镜号N：【景别】【机位】【运镜】画面：…；对白：…"
3. **素材目录**：文件按分镜号命名（`01.mp4` 或 `seg-1.mp4`），每段时长固定（默认 15 秒）
4. **目标**：单集秒数（竖屏 60/75/90）、画幅（1080×1920）、要 OpenFilm 还是剪映

## 流水线

```bash
S=<skill>/scripts
python $S/parse_storyboard.py --storyboard 分镜.xlsx --script 剧本.docx --seg 15 \
        --out film.json --report 体检报告.md
python $S/plan_episodes.py  --film film.json --target 75 --title "剧名" --out plan
python $S/build_film.py     --film film.json --plan plan.json --assets ../assets \
        --out episodes --key "绝版,滚出去" --limit 1
python $S/check_film.py     --path episodes --assets ../assets
```

**第 1 步 解析**：产出 `film.json`（每段的分镜、对白、结束状态）+ 体检报告。
**第 2 步 分集**：产出 `plan.json`、`分集工单.csv`、`分集表.xlsx`。
**第 3 步 建工程**：产出 `episodes/epNN/film.html` + `subs/zh.vtt` + `cues.md`。
**第 4 步 自检**：不通过不许渲染。

## 决策规则（这些是短剧的"手艺"，不要参数化掉）

### 分集
- **先删重复段**：分镜表里通常有 10%–15% 的重复/重述（同一动作换个角度重拍），全用会让成片"卡带"。`parse_storyboard.py` 自动标：相似度 ≥0.85，或**相邻 4 段内 ≥0.60**（补丁式填充镜头最常见），判为 `dupes` 直接删；0.6–0.85 且距离较远的是 `near`，人工判断（`--drop-near` 可一键删）。
- **按目标秒数切**：`--target 75` 得到约 5 段/集；同理 60→4 段、90→6 段。不要为了凑整集把重述段塞回去。
- **切点优先换场景**：同样接近目标长度时，切在"场景变化"处，天然是分集点。
- **集末钩子**：取该段最后一镜的**对白半句**（去掉"（画内说话）"这类标注），没有对白才用"结束状态"兜底。
- **顺序纠偏**：分镜表偶尔把后发生的镜头排在前面，用 `--order order.json`（内容如 `[1,2,3,7,4,5,9,6,10,11]`）显式指定播放顺序。
- 弱集（只有 3 段）宁可并进相邻集，也不要把一集剪成 45 秒——短剧单集低于 60 秒会显得"没内容"。

### 字幕
- 只给**有台词的镜头**，没台词的留白，不要硬塞。
- 白字 + 黑描边（VTT 里用 `text-shadow` 四向偏移 + 模糊），字号 ≈ 画面宽的 5.6%，位置 `line:82%`（不要压脸、不要贴底边）。
- 关键词标黄：`--key "绝版,滚出去,我都是为了你好"`，生成 `<c.k>` 标签。
- 句末不加句号；"……"保留；数字用阿拉伯数字；单行 ≤14 字。

### 音效（绑动作，不绑台词）
- 每集 3–6 个，只在动作发生那一帧给；同一音效一集 ≤2 次。
- 关键动作 -10~-14dB，环境音 -20~-26dB；台词一出现立刻降 6dB。
- 见 [references/sfx-library.md](references/sfx-library.md) 的"动作→音效→dB→搜索词"表。

### 配乐（必须可商用）
- **只用三类来源**：剪映「商用音乐」专区里标注可商用的 / Pixabay（可商用、免署名）/ 已购授权曲库。抖音热榜歌、榜单翻唱、来源不明的"短剧BGM合集"一律不用。
- 每集 2–3 段，切换 8–12 帧淡入淡出；铺底 -24~-20 LUFS，台词时 duck 到 -32。
- **抖音三招**（每集至少用两招）：
  1. **抽帧静音**：冲突爆点前 0.2 秒把音乐硬切断（不是淡出）。
  2. **Drop 重音**：关键动作那一帧叠一记低频 boom。
  3. **集尾空拍**：集尾 3–5 秒撤光音乐，只留环境音 + 心跳。
- 细则见 [references/music-licensing.md](references/music-licensing.md)。

### 画面
- 竖屏 1080×1920，`object-fit: cover` + `object-position: center 30%`（眼睛在上 1/3），不要拉伸变形。
- 硬切为主；情绪转折最多用 0.2 秒白闪/黑场；禁止叠化、翻页、心形转场。
- 不加片头、不加"第X集"字卡、不加平台水印。

## OpenFilm 工程写法（build_film.py 已生成，改之前先懂这三条）

- 轨道 = `<section>`，片段 = `<video>/<audio>/<img>/<iframe>`，**必须是 section 直接子元素，片段里不能包 `<div>`**。
- `at` 是它在全片里的开始秒；`#t=入,出` 是该文件自身的秒数。
- 位置只能写 `style="left;top;width;height;rotate"`；**禁止 `position`/`transform`/`margin`**。
- 字幕 = caption 轨道 `<track kind="captions" src="subs/zh.vtt" srclang="zh" label="中文">`，且这条 section 放**最前面**（轨道越前越在上层）。
- 声音 = `<audio src="…" at="T" volume="0.14">`，淡入淡出用 `overrides='[{"fade":[0.3,0.3]}]'`。
- 同一条轨道里的片段**不能重叠**；会同时响的音频要分到不同轨道。

完整语法与常见报错见 [references/film-html.md](references/film-html.md)。

## 验收（交给用户前逐条打勾）

- [ ] `check_film.py` 全部 OK（没有 FAIL）
- [ ] 每集时长与 `plan.json` 一致（段数 × 单段秒数）
- [ ] 段序与工单一致，没有重复段回流
- [ ] 字幕条数与"有台词镜头数"一致，关键词标黄
- [ ] 台词没被 BGM 压住（video volume = 1，BGM ≤ 0.15）
- [ ] 集尾卡在台词半句
- [ ] 前 3 秒有钩子（不是黑场/标题卡）

## 常见坑

1. **前 12 段顺序可能是乱的**：分镜表偶尔把"事件 B 的镜头"排在"事件 A 之前"。用 `--order order.json`（可选）显式指定播放顺序，否则先人工看一遍体检报告。
2. **字幕文字要从对白里剥掉说话人**：`build_film.py` 已做（去掉"周屿（画内说话）："）。
3. **素材比标称短**：写 `#t=0`（播到结尾），不要写 `#t=0,15` 后留黑。
4. **别用"智能成片"套模板**：会打乱分镜顺序，前功尽弃。
5. **首集单独试剪**：先 `--limit 1`，确认字幕/音乐/卡点，再批量。

## 文件索引

- scripts/parse_storyboard.py — 解析 + 查重
- scripts/plan_episodes.py — 分集 + 工单
- scripts/build_film.py — 生成 OpenFilm 工程
- scripts/check_film.py — 渲染前自检
- references/style-guide.md — 抖音/红果短剧节奏与字幕规范
- references/music-licensing.md — 可商用配乐清单与授权
- references/sfx-library.md — 音效字典
- references/film-html.md — OpenFilm 协议速查
