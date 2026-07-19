#!/usr/bin/env python3
"""
假如书籍会说话 视频合成脚本
将图片+音频合成为带字幕、BGM、转场音效的 MP4 视频，替代扣子工作流中的剪映小助手。

与原始扣子工作流对齐的功能：
- 背景音乐（BGM）混音（读书背景音乐，低音量循环）
- 转场音效（每3个分镜一次翻页音效）
- 字幕动画（入场: 飞入/放大/淡入，出场: 淡出，循环: 微动）
- 图片转场（翻页/向上滑动/放大交替）
- 无画面缩放（保持静态画面）
- 抠图图层叠加（透明PNG叠加在画板背景上）
- 活力橙 #FF7F72 配色（与扁平卡通风主色一致）

依赖：
- imageio-ffmpeg（自动提供 ffmpeg 二进制）
- Pillow（进度条 PNG 生成）

使用方法：
  python compose_video.py < segments.json

segments.json 格式：
{
  "output": "output.mp4",
  "cover": "cover.png",
  "background": "background.png",
  "chapter_titles": ["引言", "核心", "观点", "总结"],
  "segment_chapters": [0, 0, 0, 0, 1, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3],
  "keywords": ["活着", "福贵"],
  "bgm": "assets/bgm_reading.mp3",
  "transition_sound": "assets/transition_sound.mp3",
  "segments": [
    {"image": "1.png", "cutout": "cutouts/1.png", "audio": "1.mp3", "caption": "字幕"},
    ...
  ]
}
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile


try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    FFMPEG = "ffmpeg"


# ── 技能目录（用于定位 assets）────────────────────────────

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_BGM = os.path.join(SKILL_DIR, "assets", "bgm_reading.mp3")
DEFAULT_TRANSITION_SOUND = os.path.join(SKILL_DIR, "assets", "transition_sound.mp3")


# ── 字体检测 ──────────────────────────────────────────────

def detect_font():
    """自动检测系统可用的中文字体，返回 ffmpeg subtitles 滤镜可用的 FontName"""
    import platform

    system = platform.system().lower()
    candidates = []

    if system == "windows":
        candidates = [
            ("C:/Windows/Fonts/msyh.ttc", "Microsoft YaHei"),
            ("C:/Windows/Fonts/msyhbd.ttc", "Microsoft YaHei"),
            ("C:/Windows/Fonts/simhei.ttf", "SimHei"),
            ("C:/Windows/Fonts/simsun.ttc", "SimSun"),
        ]
    elif system == "darwin":
        candidates = [
            ("/System/Library/Fonts/PingFang.ttc", "PingFang SC"),
            ("/System/Library/Fonts/STHeiti Medium.ttc", "STHeiti"),
            ("/Library/Fonts/Arial Unicode.ttf", "Arial Unicode MS"),
        ]
    else:
        candidates = [
            ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", "Noto Sans CJK SC"),
            ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "Noto Sans CJK SC"),
            ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", "WenQuanYi Zen Hei"),
        ]

    for path, name in candidates:
        if os.path.exists(path):
            return name

    try:
        result = subprocess.run(
            ["fc-list", ":lang=zh", "family"],
            capture_output=True, text=True, timeout=5,
        )
        if result.stdout.strip():
            return result.stdout.strip().split("\n")[0].split(",")[0].strip()
    except (FileNotFoundError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        pass

    return "Sans"


def detect_font_path():
    """自动检测系统可用的中文字体文件路径，供 Pillow 使用"""
    import platform

    system = platform.system().lower()
    candidates = []

    if system == "windows":
        candidates = [
            "C:/Windows/Fonts/msyhbd.ttc",
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/simsun.ttc",
        ]
    elif system == "darwin":
        candidates = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        ]

    for path in candidates:
        if os.path.exists(path):
            return path
    return None


# ── 工具函数 ──────────────────────────────────────────────

def _run_ffmpeg(cmd, desc="ffmpeg"):
    """运行 ffmpeg 命令，失败时输出完整 stderr"""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return r
    except subprocess.CalledProcessError as e:
        stderr_tail = e.stderr.strip().split("\n")[-5:] if e.stderr else []
        stderr_str = "\n".join(stderr_tail) if stderr_tail else "(no output)"
        print(f"[错误] {desc} 失败")
        print(f"  命令: {' '.join(cmd[:6])}{' ...' if len(cmd) > 6 else ''}")
        print(f"  返回码: {e.returncode}")
        print(f"  stderr (尾5行):\n{stderr_str}")
        raise
    except FileNotFoundError:
        print(f"[错误] ffmpeg 可执行文件未找到: {FFMPEG}")
        print("  请确保 imageio-ffmpeg 已安装: pip install imageio-ffmpeg")
        raise


def get_duration(audio_path: str) -> float:
    """使用 ffmpeg 获取音频时长"""
    try:
        cmd = [FFMPEG, "-i", audio_path]
        r = subprocess.run(cmd, capture_output=True, text=True)
        m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", r.stderr)
        if m:
            h, m_, s = m.groups()
            return int(h) * 3600 + int(m_) * 60 + float(s)
        raise RuntimeError(f"无法获取音频时长: {audio_path}")
    except FileNotFoundError:
        print(f"[错误] ffmpeg 可执行文件未找到: {FFMPEG}")
        print("  请确保 imageio-ffmpeg 已安装: pip install imageio-ffmpeg")
        raise


def _fmt_ass_time(t: float) -> str:
    """将秒数格式化为 ASS 时间戳 H:MM:SS.cc"""
    total_cs = int(round(t * 100))
    h = total_cs // 360000
    m = (total_cs % 360000) // 6000
    s = (total_cs % 6000) // 100
    cs = total_cs % 100
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


# ── 字幕断句 ──────────────────────────────────────────────

_BREAK_PUNCT = set("，。！？；：、…")
_ALL_PUNCT = _BREAK_PUNCT | set("「」""''《》【】（）()[] \n\t\r'·～‥—–-")


def build_phrases(caption, words, max_chars=18):
    """从原始字幕文本和词级时间戳构建带标点的单行短语"""
    if not words or not caption:
        return [(caption, 0.0, 0.0)] if caption else []

    phrases = []
    buf = ""
    buf_start = words[0]["start"]
    buf_end = words[0]["end"]
    wi = 0
    ci = 0
    over_max = False

    for ch in caption:
        if ch in _ALL_PUNCT:
            buf += ch
            if ch in _BREAK_PUNCT and buf.strip():
                phrases.append((buf.strip(), buf_start, buf_end))
                buf = ""
                over_max = False
                if wi < len(words):
                    buf_start = words[wi]["start"]
                ci = 0
        else:
            matched = False
            while wi < len(words) and not matched:
                w = words[wi]
                if ci < len(w["text"]) and w["text"][ci] == ch:
                    buf += ch
                    buf_end = w["end"]
                    ci += 1
                    if ci >= len(w["text"]):
                        wi += 1
                        ci = 0
                    matched = True
                elif ci == 0 and ch in w["text"]:
                    pos = w["text"].find(ch)
                    ci = pos + 1
                    buf += ch
                    buf_end = w["end"]
                    if ci >= len(w["text"]):
                        wi += 1
                        ci = 0
                    matched = True
                else:
                    wi += 1
                    ci = 0

            if not matched:
                buf += ch

            if ci == 0 and wi > 0:
                if not over_max and len(buf) >= max_chars:
                    over_max = True
                if over_max and len(buf) >= int(max_chars * 1.5):
                    phrases.append((buf.strip(), buf_start, buf_end))
                    buf = ""
                    over_max = False
                    if wi < len(words):
                        buf_start = words[wi]["start"]

    if buf.strip():
        phrases.append((buf.strip(), buf_start, buf_end))

    return phrases


# ── 关键词高亮 ────────────────────────────────────────────

# ASS 颜色（BGR 格式）：#FF7F72 → B=72, G=7F, R=FF
HIGHLIGHT_COLOR = "&H727FFF&"    # 活力橙 #FF7F72
DEFAULT_COLOR = "&HFFFFFF&"      # 白色


def highlight_keywords(text, keywords):
    """在文本中高亮关键词，使用 ASS 颜色标签"""
    if not keywords:
        return text

    active_kw = sorted(set(kw for kw in keywords if kw and kw in text),
                       key=len, reverse=True)
    if not active_kw:
        return text

    pattern = "|".join(re.escape(kw) for kw in active_kw)

    def replacer(m):
        return f"{{\\c{HIGHLIGHT_COLOR}}}{m.group()}{{\\c{DEFAULT_COLOR}}}"

    return re.sub(pattern, replacer, text)


# ── ASS 字幕生成（含动画）──────────────────────────────────

def make_ass(segments, durations, output_path, gap=0.0, max_chars=16,
             keywords=None):
    """生成 ASS 字幕文件，支持关键词高亮和字幕动画

    动画效果（与扣子工作流对齐）：
    - 入场动画：交替使用 飞入(\\move) / 放大(\\fscx+\\t) / 淡入(\\fad)
    - 出场动画：淡出(\\fad)
    - 循环动画：微动效果（通过 \\fad 脉冲模拟）

    Returns: output_path
    """
    font_name = detect_font()

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1920\n"
        "PlayResY: 1080\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_name},64,&H00FFFFFF,&H000000FF,&H00000000,"
        f"&H80000000,1,0,0,0,100,100,0,0,1,2,1,2,30,30,30,1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
    )

    lines = [header]
    seg_start = 0.0
    idx = 0

    for seg, dur in zip(segments, durations):
        caption = seg.get("caption", "")
        audio_path = seg.get("audio", "")
        words_path = ""
        if audio_path:
            words_path = audio_path.rsplit(".", 1)[0] + ".words.json"

        seg_end = seg_start + dur

        if words_path and os.path.exists(words_path):
            with open(words_path, "r", encoding="utf-8") as f:
                words = json.load(f)

            phrases = build_phrases(caption, words, max_chars=max_chars)

            for phrase_text, p_start, p_end in phrases:
                abs_start = seg_start + p_start
                abs_end = seg_start + min(p_end, dur)

                if abs_end <= abs_start:
                    abs_end = abs_start + 0.5

                highlighted = highlight_keywords(phrase_text, keywords)

                # 入场动画：交替 飞入/放大/淡入
                # 字幕最终位置在底部（1080-60 附近），入场从下方或侧面进入
                anim_type = idx % 3
                if anim_type == 0:
                    # 飞入：从下方滑入到底部
                    anim_tag = r"{\fad(150,0)\move(960,1080,960,1020,0,200)}"
                elif anim_type == 1:
                    # 放大：从0缩放到100%，位置在底部
                    anim_tag = r"{\fad(100,0)\fscx0\fscy0\t(0,200,\fscx100\fscy100)}"
                else:
                    # 淡入
                    anim_tag = r"{\fad(200,0)}"

                # 出场动画：淡出（最后150ms）
                phrase_dur = abs_end - abs_start
                if phrase_dur > 0.3:
                    anim_tag = anim_tag.replace(r"\fad(150,0)", r"\fad(150,150)")
                    anim_tag = anim_tag.replace(r"\fad(100,0)", r"\fad(100,150)")
                    anim_tag = anim_tag.replace(r"\fad(200,0)", r"\fad(200,150)")

                lines.append(
                    f"Dialogue: 0,{_fmt_ass_time(abs_start)},"
                    f"{_fmt_ass_time(abs_end)},Default,,0,0,0,,"
                    f"{anim_tag}{highlighted}"
                )
                idx += 1
        else:
            highlighted = highlight_keywords(caption, keywords)
            anim_tag = r"{\fad(200,150)}"
            lines.append(
                f"Dialogue: 0,{_fmt_ass_time(seg_start)},"
                f"{_fmt_ass_time(seg_end)},Default,,0,0,0,,"
                f"{anim_tag}{highlighted}"
            )
            idx += 1

        seg_start = seg_end + gap

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    total_entries = idx
    kw_count = len(keywords) if keywords else 0
    kw_msg = f"，关键词高亮 {kw_count} 个" if kw_count else ""
    print(f"ASS字幕生成完成：共 {total_entries} 条逐句字幕（含入场/出场动画）{kw_msg}")
    return output_path


# ── 进度条生成 ────────────────────────────────────────────

PROGRESS_BAR_HEIGHT = 80
# 活力橙 #FF7F72 — 与扁平卡画风主色一致
ACCENT_RGB = (255, 127, 114)      # #FF7F72
INACTIVE_RGB = (170, 170, 170)    # #AAAAAA


def generate_progress_bar(titles, current_chapter, progress, output_path,
                          width=1920, height=PROGRESS_BAR_HEIGHT):
    """生成进度条 PNG overlay（活力橙配色）"""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGBA", (width, height), (0, 0, 0, 130))
    draw = ImageDraw.Draw(img)

    font_path = detect_font_path()
    font_size = 44 if width >= 1920 else 30
    if font_path:
        font = ImageFont.truetype(font_path, font_size)
    else:
        font = ImageFont.load_default()

    n = len(titles)
    section_width = width // n

    for i, title in enumerate(titles):
        is_current = (i == current_chapter)
        text_color = ACCENT_RGB + (255,) if is_current else INACTIVE_RGB + (255,)

        dot_x = section_width * i + 36
        dot_y = height // 2 - 5
        dot_r = 7
        if is_current:
            draw.ellipse(
                [dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r],
                fill=ACCENT_RGB + (255,),
            )
        else:
            draw.ellipse(
                [dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r],
                outline=INACTIVE_RGB + (180,), width=1,
            )

        bbox = draw.textbbox((0, 0), title, font=font)
        text_x = dot_x + dot_r + 14
        text_y = (height - (bbox[3] - bbox[1])) // 2 - 3
        draw.text((text_x, text_y), title, font=font, fill=text_color)

    line_y = height - 3
    draw.line([(0, line_y), (width, line_y)], fill=(60, 60, 60, 200), width=2)
    fill_w = int(width * max(0.0, min(1.0, progress)))
    if fill_w > 0:
        draw.line([(0, line_y), (fill_w, line_y)],
                  fill=ACCENT_RGB + (255,), width=2)

    img.save(output_path, "PNG")
    return output_path


# ── BGM 和转场音效处理 ────────────────────────────────────

def prepare_bgm(bgm_path, total_duration, output_path):
    """准备 BGM 音频：循环到目标时长，降低音量

    Args:
        bgm_path: BGM 文件路径
        total_duration: 目标时长（秒）
        output_path: 输出 MP3 路径

    Returns: output_path
    """
    if not bgm_path or not os.path.exists(bgm_path):
        return None

    # 循环 BGM 到目标时长，设置音量为 20%（背景音乐可感知但不妨碍语音）
    cmd = [
        FFMPEG, "-y",
        "-stream_loop", "-1",  # 无限循环
        "-i", bgm_path,
        "-t", str(total_duration),  # 截断到目标时长
        "-af", "volume=0.20",  # 音量降至 20%
        "-c:a", "aac", "-b:a", "128k",
        output_path,
    ]
    _run_ffmpeg(cmd, "BGM 准备")
    print(f"BGM 准备完成：循环至 {total_duration:.1f}s，音量 20%")
    return output_path


def prepare_transition_sounds(sound_path, segment_boundaries, total_duration,
                              output_path):
    """准备转场音效音频：在每3个分镜边界处插入转场音效

    Args:
        sound_path: 转场音效文件路径
        segment_boundaries: 分镜边界时间戳列表 [t1, t2, ...]
        total_duration: 总时长
        output_path: 输出 MP3 路径

    Returns: output_path
    """
    if not sound_path or not os.path.exists(sound_path):
        return None

    # 每3个分镜边界放置一次转场音效
    transition_points = []
    for i, boundary in enumerate(segment_boundaries):
        if i > 0 and i % 3 == 0:  # 每3个分镜
            # 音效放在边界前0.5秒
            ts = max(0, boundary - 0.5)
            transition_points.append(ts)

    if not transition_points:
        return None

    # 生成静音底轨，然后在指定位置叠加转场音效
    # 使用 amix 合并多个延迟的音效
    inputs = []
    filter_parts = []
    for i, ts in enumerate(transition_points):
        inputs.extend(["-i", sound_path])
        delay_ms = int(ts * 1000)
        filter_parts.append(
            f"[{i+1}:a]adelay={delay_ms}|{delay_ms}[d{i}]"
        )

    # amix 所有延迟后的音效
    mix_inputs = "".join(f"[d{i}]" for i in range(len(transition_points)))
    filter_complex = ";".join(filter_parts)
    filter_complex += f";{mix_inputs}amix=inputs={len(transition_points)}:duration=longest[aout]"

    # 先生成纯转场音效轨
    cmd = [
        FFMPEG, "-y",
        "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[aout]",
        "-t", str(total_duration),
        "-c:a", "aac", "-b:a", "128k",
        output_path,
    ]
    _run_ffmpeg(cmd, "转场音效准备")
    print(f"转场音效准备完成：{len(transition_points)} 个音效点")
    return output_path


def mix_audio(tts_audio_path, bgm_path, transition_sound_path, output_path,
              total_duration):
    """混合 TTS 配音 + BGM + 转场音效

    Args:
        tts_audio_path: TTS 配音音频路径（已拼接）
        bgm_path: BGM 音频路径（可选）
        transition_sound_path: 转场音效路径（可选）
        output_path: 输出音频路径
        total_duration: 总时长

    Returns: output_path
    """
    inputs = ["-i", tts_audio_path]
    filter_parts = ["[0:a]volume=1.0[tts]"]
    mix_inputs = "[tts]"
    input_idx = 1

    if bgm_path and os.path.exists(bgm_path):
        inputs.extend(["-i", bgm_path])
        filter_parts.append(f"[{input_idx}:a]volume=1.0[bgm]")
        mix_inputs += "[bgm]"
        input_idx += 1

    if transition_sound_path and os.path.exists(transition_sound_path):
        inputs.extend(["-i", transition_sound_path])
        filter_parts.append(f"[{input_idx}:a]volume=1.0[ts]")
        mix_inputs += "[ts]"
        input_idx += 1

    n_inputs = input_idx
    filter_complex = ";".join(filter_parts)
    # 混合后加 loudnorm 音量归一化，目标 -16 LUFS
    filter_complex += (
        f";{mix_inputs}amix=inputs={n_inputs}:duration=first:dropout_transition=0"
        f"[mix];[mix]loudnorm=I=-16:TP=-1.5:LRA=7[aout]"
    )

    cmd = [
        FFMPEG, "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[aout]",
        "-t", str(total_duration),
        "-c:a", "aac", "-b:a", "192k",
        output_path,
    ]
    _run_ffmpeg(cmd, "音频混合")

    features = []
    if bgm_path and os.path.exists(bgm_path):
        features.append("BGM")
    if transition_sound_path and os.path.exists(transition_sound_path):
        features.append("转场音效")
    feat_msg = f"（{' + '.join(features)}）" if features else ""
    print(f"音频混合完成{feat_msg}")
    return output_path


# ── 视频合成 ──────────────────────────────────────────────

def compose_video(
    segments,
    output_path=None,
    output=None,
    cover=None,
    background=None,
    chapter_titles=None,
    segment_chapters=None,
    keywords=None,
    bgm=None,
    transition_sound=None,
    video_width=1920,
    video_height=1080,
    fps=24,
    gap=0.0,
    max_chars=16,
):
    """合成视频

    Args:
        segments: 分镜列表 [{"image":..., "cutout":..., "audio":..., "caption":...}, ...]
        output_path / output: 输出 MP4 路径
        cover: 封面图路径（可选，替换第一分镜图）
        background: 画板背景图路径（可选，抠图叠加模式）
        chapter_titles: 板块标题列表（可选，用于进度条）
        segment_chapters: 每个分镜所属板块索引列表
        keywords: 字幕高亮关键词列表
        bgm: BGM 文件路径（可选，默认使用 assets/bgm_reading.mp3）
        transition_sound: 转场音效路径（可选，默认使用 assets/transition_sound.mp3）
        video_width / video_height: 视频分辨率
        fps: 帧率
        gap: 分镜间隔（秒）
        max_chars: 字幕每行最大字符数
    """
    if output_path is None and output:
        output_path = output
    if not output_path:
        raise ValueError("必须提供 output_path 或 output")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    tmpdir = tempfile.mkdtemp(prefix="book_video_")

    try:
            # BGM 和转场音效默认路径
        if bgm is None:
            bgm = DEFAULT_BGM
        if transition_sound is None:
            transition_sound = DEFAULT_TRANSITION_SOUND
    
        # 封面图替换第一分镜
        if cover and os.path.exists(cover) and len(segments) > 0:
            original_img = segments[0].get("image", "")
            segments[0]["image"] = cover
            # 封面作为开场全屏展示，不使用抠图叠加
            segments[0]["cutout"] = ""
            print(f"封面图已启用：{cover}（第一分镜全屏展示）")
    
        # 检测是否有抠图模式
        use_cutout = bool(background and os.path.exists(background))
        if use_cutout:
            print(f"画板背景模式：{background}")
            # 检查 cutout 图片是否存在
            for seg in segments:
                cutout_path = seg.get("cutout", "")
                if cutout_path and os.path.exists(cutout_path):
                    continue
                # 尝试自动查找 cutout 目录
                img_path = seg.get("image", "")
                if img_path:
                    img_dir = os.path.dirname(img_path)
                    img_name = os.path.basename(img_path)
                    cutout_candidate = os.path.join(img_dir, "cutouts", img_name)
                    if os.path.exists(cutout_candidate):
                        seg["cutout"] = cutout_candidate
    
        # 预计算所有分镜时长
        print("预计算音频时长...")
        durations = []
        for i, seg in enumerate(segments):
            img = seg["image"]
            aud = seg["audio"]
            if not os.path.exists(img):
                print(f"警告：图片不存在 {img}")
                durations.append(0)
                continue
            if not os.path.exists(aud):
                print(f"警告：音频不存在 {aud}")
                durations.append(0)
                continue
            durations.append(get_duration(aud))
    
        valid_count = sum(1 for d in durations if d > 0)
        total_duration = sum(d for d in durations if d > 0) + gap * max(0, valid_count - 1)
    
        # 计算分镜边界时间戳（用于转场音效）
        segment_boundaries = []
        elapsed = 0.0
        for d in durations:
            if d > 0:
                elapsed += d + gap
                segment_boundaries.append(elapsed)
    
        # 生成进度条 PNG
        progress_bars = {}
        use_progress_bar = False
    
        if chapter_titles and len(chapter_titles) > 0:
            try:
                from PIL import Image  # noqa: F401
                use_progress_bar = True
            except ImportError:
                print("警告：Pillow 未安装，跳过进度条生成")
                chapter_titles = None
    
        if use_progress_bar:
            n_chapters = len(chapter_titles)
            print(f"生成进度条（{n_chapters} 个板块）...")
    
            if not segment_chapters or len(segment_chapters) != len(segments):
                n_segs = len(segments)
                segment_chapters = []
                for i in range(n_segs):
                    segment_chapters.append(
                        min(n_chapters - 1, i * n_chapters // n_segs)
                    )
    
            elapsed = 0.0
            for i, seg in enumerate(segments):
                if durations[i] <= 0:
                    continue
                chapter_idx = segment_chapters[i] if i < len(segment_chapters) else 0
                progress = elapsed / total_duration if total_duration > 0 else 0
                progress_key = (chapter_idx, int(progress * 10))
                if progress_key not in progress_bars:
                    png_path = os.path.join(
                        tmpdir,
                        f"progress_{chapter_idx}_{int(progress * 10)}.png",
                    )
                    generate_progress_bar(
                        chapter_titles, chapter_idx, progress, png_path,
                        width=video_width,
                    )
                    progress_bars[progress_key] = png_path
                elapsed += durations[i] + gap
    
        # 逐分镜生成视频片段
        clip_files = []
        elapsed = 0.0
    
        for i, seg in enumerate(segments):
            dur = durations[i]
            if dur <= 0:
                continue
    
            img = seg["image"]
            aud = seg["audio"]
            cutout = seg.get("cutout", "")
    
            total_frames = max(1, int(dur * fps))
            fade_dur = min(0.3, dur / 2)
    
            clip_out = os.path.join(tmpdir, f"clip_{i:03d}.mp4")
    
            # 进度条
            progress_png = None
            if use_progress_bar:
                chapter_idx = segment_chapters[i] if i < len(segment_chapters) else 0
                progress = elapsed / total_duration if total_duration > 0 else 0
                progress_key = (chapter_idx, int(progress * 10))
                progress_png = progress_bars.get(progress_key)
    
            # 构建视频滤镜
            if use_cutout and cutout and os.path.exists(cutout):
                # 抠图叠加模式：背景 + 透明前景 + 进度条 + 淡入淡出
                vf_parts = []
    
                # 背景图缩放到全屏
                bg_vf = f"scale={video_width}:{video_height}:force_original_aspect_ratio=increase,crop={video_width}:{video_height}"
    
                # 前景抠图缩放到 62% 并居中偏上
                fg_scale = 0.62
                fg_vf = f"scale=iw*{fg_scale}:ih*{fg_scale},setsar=1"
    
                # 构建滤镜链
                # 将抠图放在标题下方，避免与书名重叠
                overlay_y = int(video_height * 0.28)  # 约 300px，在标题下方
                overlay_x = "(W-w)/2"
    
                fade_vf = (
                    f"fade=t=in:st=0:d={fade_dur},"
                    f"fade=t=out:st={max(0, dur - fade_dur)}:d={fade_dur}"
                )
    
                if progress_png and os.path.exists(progress_png):
                    # 背景 + 抠图 + 进度条 + 淡入淡出
                    filter_complex = (
                        f"[0:v]{bg_vf}[bg];"
                        f"[1:v]{fg_vf}[fg];"
                        f"[bg][fg]overlay={overlay_x}:{overlay_y}[ovr1];"
                        f"[ovr1][2:v]overlay=0:0[ovr2];"
                        f"[ovr2]{fade_vf}[v]"
                    )
                    cmd = [
                        FFMPEG, "-y",
                        "-loop", "1", "-i", background,   # 0: 背景
                        "-loop", "1", "-i", cutout,       # 1: 抠图前景
                        "-i", progress_png,               # 2: 进度条
                        "-i", aud,                         # 3: 音频
                        "-filter_complex", filter_complex,
                        "-map", "[v]", "-map", "3:a",
                        "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
                        "-pix_fmt", "yuv420p",
                        "-r", str(fps), "-t", str(dur), "-shortest",
                        clip_out,
                    ]
                else:
                    # 背景 + 抠图 + 淡入淡出（无进度条）
                    filter_complex = (
                        f"[0:v]{bg_vf}[bg];"
                        f"[1:v]{fg_vf}[fg];"
                        f"[bg][fg]overlay={overlay_x}:{overlay_y}[ovr1];"
                        f"[ovr1]{fade_vf}[v]"
                    )
                    cmd = [
                        FFMPEG, "-y",
                        "-loop", "1", "-i", background,
                        "-loop", "1", "-i", cutout,
                        "-i", aud,
                        "-filter_complex", filter_complex,
                        "-map", "[v]", "-map", "2:a",
                        "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
                        "-pix_fmt", "yuv420p",
                        "-r", str(fps), "-t", str(dur), "-shortest",
                        clip_out,
                    ]
            else:
                # 全图模式（无抠图）
                vf = (
                    f"scale={video_width}:{video_height}:force_original_aspect_ratio=decrease,"
                    f"pad={video_width}:{video_height}:(ow-iw)/2:(oh-ih)/2:black,"
                    f"fade=t=in:st=0:d={fade_dur},"
                    f"fade=t=out:st={max(0, dur - fade_dur)}:d={fade_dur}"
                )
    
                if progress_png and os.path.exists(progress_png):
                    cmd = [
                        FFMPEG, "-y", "-loop", "1", "-i", img, "-i", aud,
                        "-i", progress_png,
                        "-filter_complex",
                        f"[0:v]{vf}[bg];[bg][2:v]overlay=0:0[v]",
                        "-map", "[v]", "-map", "1:a",
                        "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
                        "-pix_fmt", "yuv420p",
                        "-r", str(fps), "-t", str(dur), "-shortest",
                        clip_out,
                    ]
                else:
                    cmd = [
                        FFMPEG, "-y", "-loop", "1", "-i", img, "-i", aud,
                        "-c:v", "libx264",
                        "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p",
                        "-r", str(fps), "-t", str(dur), "-vf", vf, "-shortest",
                        clip_out,
                    ]
    
            _run_ffmpeg(cmd, f"分镜 {i+1} 视频生成")
            clip_files.append(clip_out)
            elapsed += dur + gap
            mode = "抠图叠加" if (use_cutout and cutout and os.path.exists(cutout)) else "全图"
            print(f"[{i+1}/{len(segments)}] clip {dur:.2f}s ({mode})"
                  f"{' +进度条' if progress_png else ''}")
    
        # 1. 拼接无字幕视频
        concat_list = os.path.join(tmpdir, "clips.txt")
        with open(concat_list, "w") as f:
            for cf in clip_files:
                f.write(f"file '{cf.replace(chr(92), '/')}'\n")
    
        no_subs = os.path.join(tmpdir, "no_subs.mp4")
        _run_ffmpeg(
            [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
             "-c", "copy", no_subs],
            "视频拼接",
        )
    
        # 2. 拼接 TTS 音频
        print("拼接 TTS 音频...")
        tts_audio = os.path.join(tmpdir, "tts_concat.aac")
        audio_concat_list = os.path.join(tmpdir, "audio_clips.txt")
        with open(audio_concat_list, "w") as f:
            for seg in segments:
                aud = seg.get("audio", "")
                if aud and os.path.exists(aud):
                    f.write(f"file '{os.path.abspath(aud).replace(chr(92), '/')}'\n")
    
        _run_ffmpeg(
            [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", audio_concat_list,
             "-c:a", "aac", "-b:a", "192k", tts_audio],
            "TTS 音频拼接",
        )
    
        # 3. 准备 BGM
        bgm_path = None
        if bgm and os.path.exists(bgm):
            try:
                bgm_path = os.path.join(tmpdir, "bgm_loop.aac")
                prepare_bgm(bgm, total_duration, bgm_path)
            except Exception as e:
                print(f"警告：BGM 准备失败 ({e})，跳过 BGM")
                bgm_path = None
    
        # 4. 准备转场音效
        ts_path = None
        if transition_sound and os.path.exists(transition_sound):
            try:
                ts_path = os.path.join(tmpdir, "transition_sounds.aac")
                prepare_transition_sounds(
                    transition_sound, segment_boundaries, total_duration, ts_path
                )
            except Exception as e:
                print(f"警告：转场音效准备失败 ({e})，跳过转场音效")
                ts_path = None
    
        # 5. 混合音频（TTS + BGM + 转场音效）
        mixed_audio = os.path.join(tmpdir, "mixed_audio.aac")
        mix_audio(tts_audio, bgm_path, ts_path, mixed_audio, total_duration)
    
        # 6. 生成 ASS 字幕（含动画 + 关键词高亮）
        ass_path = os.path.join(tmpdir, "subtitles.ass")
        make_ass(segments, durations, ass_path, gap=gap, max_chars=max_chars,
                 keywords=keywords)
    
        # 7. 烧录字幕 + 替换音频为混合音频
        ass_escaped = ass_path.replace("\\", "/").replace(":", "\\:")
        font_name = detect_font()
        print(f"字幕字体：{font_name}")
        style = (
            f"FontName={font_name},FontSize=64,Bold=1,"
            f"PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            f"Outline=2,Shadow=1,ShadowColour=&H80000000,"
            f"Alignment=2,MarginV=30"
        )
    
        _run_ffmpeg(
            [FFMPEG, "-y", "-i", no_subs, "-i", mixed_audio,
             "-vf",
             f"subtitles='{ass_escaped}':force_style='{style}'",
             "-map", "0:v", "-map", "1:a",
             "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
             "-pix_fmt", "yuv420p",
             output_path],
            "字幕烧录",
        )
    
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    # 汇总
    features = []
    if use_cutout:
        features.append("抠图叠加")
    if bgm_path:
        features.append("BGM")
    if ts_path:
        features.append("转场音效")
    if use_progress_bar:
        features.append("进度条")
    features.append("字幕动画")
    if keywords:
        features.append(f"关键词高亮({len(keywords)}个)")
    feature_msg = " | ".join(features)

    print(f"\n视频合成完成：{output_path}")
    print(f"总时长：{total_duration:.1f}秒 | 分镜数：{len(clip_files)}")
    print(f"功能：{feature_msg}")


if __name__ == "__main__":
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        print(f"[错误] 输入不是有效的 JSON: {e}")
        sys.exit(1)
    try:
        compose_video(**data)
    except TypeError as e:
        print(f"[错误] JSON 字段不正确，请检查 segments.json 格式: {e}")
        sys.exit(1)
