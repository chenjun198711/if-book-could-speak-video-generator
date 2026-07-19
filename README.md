# 假如书籍会说话 (If Books Could Speak)

让书籍"开口说话"——以第一人称视角，生成书籍自述视频。

书自己讲述它的诞生故事、核心智慧、难忘场景和情感共鸣，仿佛它是一个有灵魂的生命体在和你对话。

## 效果演示

输入：书名 + 作者
输出：约 3 分钟书籍第一人称自述视频（MP4）

```
书评文案（第一人称）→ AI 扁平卡通插图 → TTS 配音 → 抠图+画板叠加 → 逐句字幕动画 → BGM+转场音效 → 最终合成 MP4
```

## 与 book-video-generator 的区别

| 维度 | 假如书籍会说话 | 三分钟精读一本书 |
|------|--------------|----------------|
| 叙事视角 | **第一人称（书自述）** | 第三人称（博主解读） |
| 画面风格 | 扁平卡通插画 | 扁平卡通插画 |
| 配色主题 | 活力橙 #FF7F72 + 深墨蓝 #243139 | 活力橙 #FF7F72 + 深墨蓝 #243139 |
| 开场白 | "你好，我是《书名》…" | "3分钟精读一本书，今天我们读…" |
| 语气基调 | 亲切对话、情感共鸣 | 专业解读、知识提炼 |
| 画板+抠图 | 有（rembg AI 抠图） | 无 |
| BGM | 有（循环读书背景音乐） | 无 |
| 转场音效 | 有（翻页音效） | 无 |
| 字幕动画 | 入场/出场/关键词高亮 | 无（仅基础字幕） |

## 文件结构

```
if-book-could-speak/
├── SKILL.md                          # 技能主指令（5阶段工作流 + 平台映射）
├── README.md                         # 本文件
├── assets/
│   ├── bgm_reading.mp3               # 内置读书背景音乐
│   └── transition_sound.mp3          # 内置翻页转场音效
├── references/
│   ├── prompts.md                    # 3个第一人称LLM提示词 + 图像风格参数
│   ├── CROSS_PLATFORM.md             # 5平台适配指南
│   └── workflow-original.yaml        # 原始扣子工作流完整YAML
└── scripts/
    ├── generate_image.py             # 跨平台AI图像生成（自动追加扁平卡通风格后缀）
    ├── generate_audio.py             # TTS语音生成（知性女声默认，1.2x语速）
    ├── generate_cover.py             # 封面图生成（活力橙深蓝主题）
    ├── generate_background.py        # 画板背景图生成（对应扣子 drawing_board）
    ├── cutout.py                     # AI抠图脚本（rembg主方案+PIL备选）
    └── compose_video.py              # 视频合成（画板+抠图+BGM+转场音效+字幕动画）
```

## 快速开始

### 环境准备

```bash
pip install edge-tts imageio-ffmpeg pillow rembg onnxruntime
```

> `rembg` + `onnxruntime` 用于 AI 抠图（U2Net 模型），首次使用会自动下载模型（约 170MB）。若无法安装 rembg，抠图脚本会自动回退到 PIL 颜色阈值法。

可选：配置火山引擎 TTS（中文自然度更高，未配置则自动使用免费 edge-tts）

```bash
# 方式一：写入配置文件（推荐，一次配置永久生效）
echo "your-api-key" > ~/.workbuddy/skills/if-book-could-speak/.tts_key

# 方式二：设置环境变量
export VOLC_TTS_API_KEY="your-api-key"
```

### 使用

在 WorkBuddy 中说：

> "帮我生成《小王子》Antoine de Saint-Exupery 的假如书籍会说话视频"

技能会自动执行 5 个阶段：

1. 搜索书籍信息 → 生成第一人称自述文案（"你好，我是《小王子》…"）
2. 将文案拆分为分镜脚本（扁平卡通画风描述）
3. 生成 4 个情感板块标题
4. 并行生成：AI 插图 + TTS 配音 + 封面图 + 画板背景 + AI 抠图
5. ffmpeg 合成最终视频（画板+抠图+BGM+转场音效+字幕动画）

输出：`output/小王子_假如书籍会说话.mp4`

## 技术栈

- **视频合成**：ffmpeg（通过 imageio-ffmpeg 自动提供二进制）
- **TTS**：火山引擎 TTS 2.0（默认，知性女声，1.2x 语速）/ edge-tts（备选，免费）
- **图像生成**：平台内置 ImageGen / 外部 API（DALL-E / Stability AI / 火山引擎 / 本地 SD）
- **AI抠图**：rembg（U2Net 模型）/ PIL（备选颜色阈值法）
- **封面/进度条**：Pillow（PIL）
- **字幕**：ASS 格式，词级时间戳精确同步，入场/出场动画，关键词高亮

## 跨平台兼容

| 平台 | 状态 |
|------|------|
| WorkBuddy | 原生支持 |
| OpenClaw | 兼容 |
| Codex CLI | 兼容（使用 generate_image.py） |
| TRAE Work | 兼容（通过 MCP 接入图像生成） |
| Claude Code | 兼容 |

## 许可证

MIT License - Copyright (c) 2026
