#!/usr/bin/env python3
"""
抠图脚本 — 假如书籍会说话

模拟原始扣子工作流中的 cutout 插件，将分镜图片的背景移除，
生成透明背景 PNG，用于叠加在画板背景图上方。

主方案：rembg（基于 U2Net 模型的 AI 抠图，效果最佳）
备选方案：PIL 颜色阈值法（适用于扁平卡通图片的简单背景移除）

依赖：
- rembg + onnxruntime（主方案，首次使用需下载模型）
- Pillow（备选方案）

使用方法：
  python cutout.py --input scene_001.png --output scene_001_cutout.png
  python cutout.py --batch images/ --output-dir cutouts/
"""

import argparse
import os
import sys


def cutout_with_rembg(input_path: str, output_path: str) -> str:
    """使用 rembg 进行 AI 抠图（主方案）

    rembg 基于 U2Net 模型，能精确识别前景主体并移除背景。
    首次使用时会自动下载模型（~170MB）。
    """
    from rembg import remove, new_session
    from PIL import Image

    # 创建会话（首次会下载模型）
    session = new_session("u2net")

    img = Image.open(input_path)
    result = remove(img, session=session)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    result.save(output_path, "PNG")
    return output_path


def cutout_with_pil(input_path: str, output_path: str,
                    threshold: int = 240) -> str:
    """使用 PIL 颜色阈值法进行简单抠图（备选方案）

    适用于背景为浅色/白色的扁平卡通图片。
    将亮度高于阈值的像素设为透明。
    """
    from PIL import Image

    img = Image.open(input_path).convert("RGBA")
    pixels = img.load()
    width, height = img.size

    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            # 亮度计算
            brightness = (r * 0.299 + g * 0.587 + b * 0.114)
            if brightness > threshold:
                # 浅色背景 → 透明
                alpha = int(max(0, 255 - (brightness - threshold) * 4))
                pixels[x, y] = (r, g, b, alpha)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    img.save(output_path, "PNG")
    return output_path


def cutout_image(input_path: str, output_path: str,
                 method: str = "auto") -> str:
    """抠图统一接口

    Args:
        input_path: 输入图片路径
        output_path: 输出透明背景 PNG 路径
        method: "auto" | "rembg" | "pil"

    Returns: output_path
    """
    if method == "auto":
        # 优先使用 rembg，不可用时回退到 PIL
        try:
            import rembg  # noqa: F401
            method = "rembg"
        except ImportError:
            method = "pil"

    if method == "rembg":
        try:
            return cutout_with_rembg(input_path, output_path)
        except Exception as e:
            print(f"  rembg 抠图失败({e})，回退到 PIL 方案")
            return cutout_with_pil(input_path, output_path)
    else:
        return cutout_with_pil(input_path, output_path)


def batch_cutout(input_dir: str, output_dir: str,
                 pattern: str = "scene_*.png",
                 method: str = "auto") -> list:
    """批量抠图

    Args:
        input_dir: 输入目录
        output_dir: 输出目录
        pattern: 文件匹配模式
        method: 抠图方法

    Returns: [output_path, ...]
    """
    import glob

    files = sorted(glob.glob(os.path.join(input_dir, pattern)))
    if not files:
        print(f"未找到匹配文件：{os.path.join(input_dir, pattern)}")
        return []

    os.makedirs(output_dir, exist_ok=True)
    results = []

    for i, fpath in enumerate(files):
        fname = os.path.basename(fpath)
        output = os.path.join(output_dir, fname)
        try:
            cutout_image(fpath, output, method)
            results.append(output)
            print(f"[{i+1}/{len(files)}] {fname} → {output}")
        except Exception as e:
            print(f"[{i+1}/{len(files)}] {fname} FAILED: {e}")
            results.append(None)

    return results


# ── CLI ───────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="抠图脚本（rembg/PIL 双方案）")
    parser.add_argument("--input", type=str, help="输入图片路径")
    parser.add_argument("--output", type=str, help="输出透明背景 PNG 路径")
    parser.add_argument("--batch", type=str, help="批量模式：输入目录")
    parser.add_argument("--output-dir", type=str, help="批量输出目录")
    parser.add_argument("--pattern", default="scene_*.png", help="批量匹配模式")
    parser.add_argument("--method", choices=["auto", "rembg", "pil"],
                        default="auto", help="抠图方法（默认 auto）")
    parser.add_argument("--threshold", type=int, default=240,
                        help="PIL 方案的亮度阈值（默认 240）")

    args = parser.parse_args()

    if args.batch:
        batch_cutout(args.batch, args.output_dir or "cutouts",
                     args.pattern, args.method)
    elif args.input and args.output:
        if args.method == "pil":
            cutout_with_pil(args.input, args.output, args.threshold)
        else:
            cutout_image(args.input, args.output, args.method)
        print(f"抠图完成：{args.output}")
    else:
        print("请提供 --input/--output 或 --batch/--output-dir 参数")
        sys.exit(1)
