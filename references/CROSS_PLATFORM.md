# 跨平台适配指南

本文件详细说明 `if-book-could-speak`（假如书籍会说话）技能在各 AI Agent 平台上的安装和适配方法。

技能遵循 [Agent Skills 开放标准](https://agentskills.io)，核心组件（SKILL.md 格式、LLM 提示词、Python 脚本）跨平台通用，仅需适配平台专有工具。

---

## 平台兼容性总览

| 组件 | WorkBuddy | OpenClaw | Codex CLI | TRAE Work |
|------|-----------|----------|-----------|-----------|
| SKILL.md 格式 | 原生 | 兼容 | 兼容 | 兼容 |
| LLM 提示词 | 直接用 | 直接用 | 直接用 | 直接用 |
| Python 脚本 | 直接用 | 直接用 | 直接用 | 直接用 |
| 联网搜索 | WebSearch | 内置 | Shell/MCP | 内置 |
| 图像生成 | ImageGen | 插件 | generate_image.py | MCP |
| 技能目录 | ~/.workbuddy/skills/ | ~/.openclaw/skills/ | ~/.codex/skills/ | ~/.trae/skills/ |

---

## 1. WorkBuddy（当前平台）

无需额外配置，技能已安装。

- 联网搜索：内置 `WebSearch` 工具
- 图像生成：内置 `ImageGen` 延迟工具（通过 ToolSearch + DeferExecuteTool 调用）
- Python 运行：使用托管 Python

---

## 2. OpenClaw

### 安装

```bash
# 直接复制
cp -r ~/.workbuddy/skills/if-book-could-speak ~/.openclaw/skills/
```

### 工具适配

OpenClaw 支持在 SKILL.md frontmatter 中声明 `tools`。如需原生图像生成，可在 frontmatter 中添加：

```yaml
tools:
  - name: generate_image
    description: "根据提示词生成扁平卡通风格插图"
    handler: ./scripts/generate_image.py
    parameters:
      prompt:
        type: string
        required: true
      output:
        type: string
        required: true
```

联网搜索：OpenClaw 内置 web search 能力，无需额外配置。

---

## 3. Codex CLI（OpenAI）

### 安装

```bash
# 1. 开启 Skills 功能
cat >> ~/.codex/config.toml << 'EOF'
[features]
skills = true
EOF

# 2. 复制技能目录
cp -r ~/.workbuddy/skills/if-book-could-speak ~/.codex/skills/

# 3. 重启 Codex CLI，输入 /skills 确认已加载
```

### 工具适配

**联网搜索**：Codex CLI 无内置搜索，两种方案：
- 方案 A — Shell 命令搜索（免安装）
- 方案 B — 安装搜索 MCP 插件

**图像生成**：使用 `scripts/generate_image.py`：

```bash
# 设置 API Key（任选其一）
export OPENAI_API_KEY="sk-..."
# 或
export STABILITY_API_KEY="sk-..."
# 或
export IMAGE_API="local" SD_WEBUI_URL="http://127.0.0.1:7860"

# 生成单张（脚本会自动追加扁平卡通风格后缀）
python3 scripts/generate_image.py --prompt "描述" --output "scene_001.png"

# 批量生成
python3 scripts/generate_image.py --batch output/书名/02_storyboard.json --output-dir output/书名/images/
```

---

## 4. TRAE Work（字节跳动）

### 安装

```
1. 打开 TRAE Work IDE
2. 进入「规则和技能 → 技能 → 创建」
3. 选择「导入文件」，上传 SKILL.md
4. 将 scripts/、references/、assets/ 目录复制到技能目录下
```

技能目录结构：
```
~/.trae/skills/
  if-book-could-speak/
    SKILL.md
    scripts/
      compose_video.py
      generate_audio.py
      generate_image.py
      generate_cover.py
      generate_background.py
      cutout.py
    references/
      prompts.md
      CROSS_PLATFORM.md
      workflow-original.yaml
    assets/
      bgm_reading.mp3
      transition_sound.mp3
```

### 工具适配

**联网搜索**：TRAE Work 内置联网搜索能力，直接可用。

**图像生成**：通过 MCP 接入图像生成服务，或使用 `scripts/generate_image.py` + 环境变量方式。

---

## 5. 其他兼容平台

- **Claude Code** — `~/.claude/skills/`
- **Cursor** — 支持 Agent Skills 标准
- **GitHub Copilot** — 支持 Agent Skills 标准

安装方式统一为：将技能目录复制到对应平台的 skills 目录下。

---

## 通用注意事项

### Python 环境

所有平台执行脚本时使用 `python3`（或 Windows 上的 `python`）。确保以下依赖已安装：

```bash
pip install edge-tts imageio-ffmpeg pillow rembg onnxruntime
```

> `rembg` + `onnxruntime` 用于 AI 抠图。若无法安装 rembg，抠图脚本会自动回退到 PIL 颜色阈值法。

TTS 引擎配置（可选）：
- **火山引擎 TTS**（默认）：将 API Key 写入 `.tts_key` 文件（推荐）或设置环境变量 `VOLC_TTS_API_KEY`
- **edge-tts**（备选）：无需配置，未设置火山引擎凭证时自动使用

### 字体

视频字幕烧录和封面图均需要中文字体支持，脚本已实现自动检测：

| 系统 | 字体路径 | FontName |
|------|----------|----------|
| Windows | C:/Windows/Fonts/msyh.ttc | Microsoft YaHei |
| macOS | /System/Library/Fonts/PingFang.ttc | PingFang SC |
| Linux | /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc | Noto Sans CJK SC |

### 与 book-video-generator 的区别

本技能与 `book-video-generator` 共享相同的技术管线（ffmpeg + TTS + Python 脚本），但创意方向和视觉增强完全不同：

| 维度 | if-book-could-speak | book-video-generator |
|------|---------------------|---------------------|
| 品牌文字 | 假如书籍会说话 | 3分钟精读一本书 |
| 叙事视角 | **第一人称（书自述）** | 第三人称（博主解读） |
| 画面风格 | 扁平卡通插画 | 扁平卡通插画 |
| 配色主题 | 活力橙 #FF7F72 + 深墨蓝 #243139 | 活力橙 #FF7F72 + 深墨蓝 #243139 |
| 开场白 | "你好，我是《书名》…" | "3分钟精读一本书，今天我们读…" |
| 画板+抠图 | 有（rembg AI 抠图 + 画板背景） | 无 |
| BGM | 有（循环读书背景音乐，20% 音量） | 无 |
| 转场音效 | 有（翻页音效，每 3 个分镜） | 无 |
| 字幕动画 | 入场/出场/关键词高亮 | 基础字幕 |
| 输出文件名 | 书名_假如书籍会说话.mp4 | 书名_三分钟精读书.mp4 |

两个技能可以共存，用户根据创意需求选择使用。

---

## 版本历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-07-18 | 1.0 | 基于 book-video-generator 技术管线，重构创意方向为"假如书籍会说话"第一人称书籍自述 |
| 2026-07-19 | 2.1.0 | 移除 Ken Burns 缩放；修正品牌文字；加入 BGM、转场音效、画板抠图、字幕动画；全面跨平台审查 |
