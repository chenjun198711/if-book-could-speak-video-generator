#!/usr/bin/env python3
"""
画板背景图生成脚本 — 假如书籍会说话

模拟原始扣子工作流中的 drawing_board 节点，生成包含书名、作者、年份、
分类、4个板块标题的画板背景图（1920x1080）。

抠图后的分镜图片（透明背景PNG）将叠加在此背景图上方，形成分层视觉效果。

依赖：Pillow (PIL)

使用方法：
  python generate_background.py --book-name "活着" --author "余华" \\
      --year "1992-01" --category "文学小说" \\
      --titles "引言" "核心" "观点" "总结" \\
      --output background.png
"""

import argparse
import os
import platform
import sys

from PIL import Image, ImageDraw, ImageFont


# ── 字体检测 ──────────────────────────────────────────────

def detect_font_path():
    """自动检测系统可用的中文字体文件路径"""
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
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        ]

    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def load_font(size):
    """加载指定大小的中文字体"""
    font_path = detect_font_path()
    if font_path:
        return ImageFont.truetype(font_path, size)
    print("警告：未找到中文字体，使用默认字体", file=sys.stderr)
    return ImageFont.load_default()


# ── 颜色定义 ──────────────────────────────────────────────

# 活力橙 #FF7F72 — 与扁平卡通风主色一致
ACCENT_RGB = (255, 127, 114)
# 深蓝背景 #0F1726
BG_DARK = (15, 23, 38)
BG_LIGHT = (30, 41, 59)
# 白色文字
WHITE = (255, 255, 255)
LIGHT_GRAY = (200, 210, 225)


def draw_text_centered(draw, text, y, font, img_width, fill=WHITE, shadow=True):
    """居中绘制文字，可选阴影"""
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    x = (img_width - text_width) // 2
    if shadow:
        draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, 160))
    draw.text((x, y), text, font=font, fill=fill)


def wrap_text(draw, text, font, max_width):
    """将文本按最大宽度自动换行"""
    lines = []
    current = ""
    for char in text:
        test = current + char
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > max_width and current:
            lines.append(current)
            current = char
        else:
            current = test
    if current:
        lines.append(current)
    return lines


# ── 主函数 ────────────────────────────────────────────────

def generate_background(
    book_name,
    author_name,
    year="",
    category="",
    titles=None,
    output_path="background.png",
    width=1920,
    height=1080,
):
    """
    生成画板背景图

    布局（模拟扣子 drawing_board）：
    - 顶部：书名（大字）
    - 中部左侧：4个板块标题（竖向排列）
    - 中部右侧：作者、年份、分类信息
    - 背景：深蓝色渐变
    """
    if titles is None:
        titles = ["引言", "核心", "观点", "总结"]
    # 兼容命令行传入逗号分隔字符串的情况：--titles "初见,故事,感悟,共鸣"
    if len(titles) == 1 and "," in titles[0]:
        titles = [t.strip() for t in titles[0].split(",") if t.strip()]

    # 1. 深蓝色渐变背景
    img = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        ratio = y / height
        r = int(BG_DARK[0] + (BG_LIGHT[0] - BG_DARK[0]) * ratio)
        g = int(BG_DARK[1] + (BG_LIGHT[1] - BG_DARK[1]) * ratio)
        b = int(BG_DARK[2] + (BG_LIGHT[2] - BG_DARK[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

    # 2. 顶部品牌文字（避开顶部 80px 进度条区域）
    brand_font = load_font(32)
    draw_text_centered(draw, "假如书籍会说话", 100, brand_font, width,
                       fill=LIGHT_GRAY)

    # 活力橙分隔线
    line_y = 150
    line_w = min(360, width // 4)
    line_x = (width - line_w) // 2
    draw.line([(line_x, line_y), (line_x + line_w, line_y)],
              fill=ACCENT_RGB + (230,), width=3)

    # 3. 书名（大字居中，位于进度条与中部抠图之间）
    title_font = load_font(72)
    max_title_width = width - 300
    title_lines = wrap_text(draw, f"《{book_name}》", title_font, max_title_width)
    line_height = int(72 * 1.3)
    title_top = 170
    for i, line in enumerate(title_lines):
        draw_text_centered(draw, line, title_top + i * line_height,
                           title_font, width, fill=WHITE)

    # 4. 板块标题（左侧竖向排列，中部区域）
    chapter_font = load_font(28)
    chapter_start_y = int(height * 0.45)
    chapter_spacing = 50
    chapter_x = 80

    for i, title in enumerate(titles[:4]):
        y = chapter_start_y + i * chapter_spacing
        # 板块编号圆点
        dot_r = 8
        dot_x = chapter_x + dot_r
        dot_y = y + 14
        draw.ellipse(
            [dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r],
            fill=ACCENT_RGB + (255,),
        )
        # 板块标题文字
        draw.text((dot_x + dot_r + 12, y), f"{i+1}. {title}",
                  font=chapter_font, fill=LIGHT_GRAY)

    # 5. 右侧信息（作者、年份、分类）
    info_font = load_font(26)
    info_x = width - 400
    info_y = int(height * 0.45)

    infos = []
    if author_name:
        infos.append(f"作者：{author_name}")
    if year:
        infos.append(f"出版：{year}")
    if category:
        infos.append(f"分类：{category}")

    for i, info in enumerate(infos):
        draw.text((info_x, info_y + i * 40), info,
                  font=info_font, fill=LIGHT_GRAY)

    # 6. 底部装饰线
    bottom_line_y = height - 60
    draw.line([(100, bottom_line_y), (width - 100, bottom_line_y)],
              fill=ACCENT_RGB + (100,), width=1)

    # 7. 保存
    img.convert("RGB").save(output_path, "PNG", quality=95)
    print(f"画板背景图已生成：{output_path}  ({width}x{height})")
    return output_path


# ── CLI ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="生成画板背景图（模拟扣子 drawing_board）")
    parser.add_argument("--book-name", required=True, help="书名")
    parser.add_argument("--author", required=True, help="作者名")
    parser.add_argument("--year", default="", help="出版年份（如 1992-01）")
    parser.add_argument("--category", default="", help="图书分类")
    parser.add_argument("--titles", nargs="+", default=["引言", "核心", "观点", "总结"],
                        help="4个板块标题")
    parser.add_argument("--output", required=True, help="输出 PNG 路径")
    parser.add_argument("--width", type=int, default=1920, help="宽度")
    parser.add_argument("--height", type=int, default=1080, help="高度")

    args = parser.parse_args()
    generate_background(
        book_name=args.book_name,
        author_name=args.author,
        year=args.year,
        category=args.category,
        titles=args.titles,
        output_path=args.output,
        width=args.width,
        height=args.height,
    )


if __name__ == "__main__":
    main()
