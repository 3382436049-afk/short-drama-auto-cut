# OpenFilm 协议 0.1 速查（写 film.html 之前先看这页）

OpenFilm 的片子 = 一个 `film.html`：HTML 说"哪个片段何时何地播"，CSS 说"长什么样"。
它是**严格解析**的：拼错一个属性、多一个杂元素，会被报错而不是忽略。

## 最小可用骨架

```html
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=1080, height=1920">
<style>
  video { object-fit: cover; object-position: center 30%; }
  @keyframes push { from { scale: 1 } to { scale: 1.03 } }
</style>
</head>
<body>
  <section><track kind="captions" src="subs/zh.vtt" srclang="zh" label="中文"></section>
  <section>
    <video src="../assets/01.mp4#t=0,15" at="0" volume="1"
           style="left:0;top:0;width:1080px;height:1920px;animation:push 15s linear both"></video>
  </section>
  <section>
    <audio src="../assets/bgm.mp3#t=0,9" at="0" volume="0.14" overrides='[{"fade":[0.3,0]}]'></audio>
  </section>
</body>
</html>
```

## 属性表

| 属性 | 作用 | 注意 |
|---|---|---|
| `src` | 文件 + 媒体片段 `#t=入,出` | 秒数是**文件自身**的，不是全片的 |
| `at` | 在全片里的开始秒 | 默认 0 |
| `speed` | 播放速率 0.1–100 | 片段时长 = (出−入)/speed |
| `volume` | 线性增益 0–1 | 0.5≈-6dB、0.25≈-12dB、0.12≈-18dB |
| `style` | `left/top/width/height/rotate` | **只能用这四个半** |
| `overrides` | JSON：`fade` / `text` / `split` / `style` | `fade:[入,出]` 秒 |
| `disabled` | 不画不放，但保留时长 | 调试用 |
| `muted`/`hidden`/`locked` | 轨道级 | 人手动改，agent 不要动 |

## 结构规则

- 轨道 = `<section>`，**越靠前越在上层**。字幕轨放最前。
- 片段是 section 的**直接子元素**，且**片段里不能包任何元素**。
- 同一条轨道里的片段**不能重叠**；画中画/字幕/同时响的音效各占一条轨道。
- 字幕 = `<track kind="captions" src="…vtt">`，一整条 section 只放它。
- 声音 = `<audio>` 或 `<video>` 自带音轨；一个页面的声音不会被录进去。

## 字幕（WebVTT）要点

```
WEBVTT

STYLE
::cue { font-weight:700; color:#fff; text-shadow: 2px 2px 0 #000, -2px 2px 0 #000, 2px -2px 0 #000, -2px -2px 0 #000; }
::cue(.k) { color:#FFD400; }

NOTE Each cue is one subtitle, as cut by hand in OpenFilm Studio.

1
00:00:03.000 --> 00:00:06.000 line:82% position:50% size:86% align:center
妈，别动！那是<c.k>绝版</c>的！
```

- cue 设置：`line:82% position:50% size:86% align:center`
- 关键词高亮：`<c.k>` + `::cue(.k)`
- 文件头带 `NOTE Each cue is one subtitle…`，编辑器会按你切的整行显示

## 五个必错的坑

1. `<section><div><video …></div></section>` → 片段里不能有元素，报错。
2. `style="position:absolute; transform:translateX(10px)"` → 位置只能用 left/top/width/height/rotate。
3. `#t=` 写成全片时间 → 它读的是文件自身时间，成片会错位。
4. 字幕 section 放在视频后面 → 被画面盖住。
5. 同一条音频轨里两段重叠 → 报错；同时响的拆到不同 section。

## 渲染

在 OpenFilm Studio 里打开工程目录，预览确认后导出 mp4（1080×1920、30fps）。
`check_film.py` 能提前抓掉上面五类错误，别等到渲染失败。
