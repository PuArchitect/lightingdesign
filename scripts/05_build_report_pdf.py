#!/usr/bin/env python3
"""
Stage 5 & 6: HTML -> 无头浏览器 PDF + 页码压印 + 清理元数据 + 导出质检 PNG (lightingdesign v2.0)
"""

import argparse
import json
import subprocess
from pathlib import Path
import fitz  # pymupdf


def html_to_pdf(browser_exe: str, html_path: Path, raw_pdf: Path) -> None:
    cmd = [
        browser_exe,
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={raw_pdf.resolve()}",
        html_path.resolve().as_uri(),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not raw_pdf.is_file():
        raise RuntimeError(f"无头浏览器打印失败: {res.stderr}")


def stamp_and_clean_pdf(
    raw_pdf: Path,
    out_pdf: Path,
    formal_title: str,
    stamp_page_num: bool = True,
    qc_png_dir: Path | None = None,
) -> None:
    doc = fitz.open(raw_pdf)
    total = len(doc)

    for idx, page in enumerate(doc, start=1):
        if stamp_page_num:
            rect = page.rect
            label = f"{idx:02d} / {total:02d}"
            page.insert_text(
                (rect.width - 60, rect.height - 12),
                label,
                fontsize=8.0,
                color=(0.35, 0.35, 0.35),
            )
        if qc_png_dir:
            qc_png_dir.mkdir(parents=True, exist_ok=True)
            pix = page.get_pixmap(dpi=120)
            pix.save(qc_png_dir / f"page_{idx:02d}.png")

    doc.set_metadata({"title": formal_title, "author": "", "creator": "", "producer": ""})
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_pdf, garbage=4, deflate=True)
    doc.close()
    print(f"[Stage 5] 正式 PDF 已输出 ({total} 页): {out_pdf}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 5 HTML转PDF与元数据清理")
    parser.add_argument("--env", required=True, help="env_fingerprint.json 路径")
    parser.add_argument("--html", required=True, help="输入 HTML 路径")
    parser.add_argument("--out-pdf", required=True, help="输出正式 PDF 路径")
    parser.add_argument("--title", required=True, help="PDF 正式标题")
    parser.add_argument("--no-page-num", action="store_true", help="A3 单页图纸可跳过页码压印")
    parser.add_argument("--qc-dir", default="", help="可选：导出 120dpi 视觉质检 PNG 目录")
    args = parser.parse_args()

    env_data = json.loads(Path(args.env).read_text(encoding="utf-8"))
    browser = env_data.get("headless_browser")
    if not browser:
        raise RuntimeError("env_fingerprint.json 中未找到可用无头浏览器，无法打印 PDF。")

    raw_pdf = Path(args.out_pdf).with_suffix(".raw.pdf")
    html_to_pdf(browser, Path(args.html), raw_pdf)
    stamp_and_clean_pdf(
        raw_pdf,
        Path(args.out_pdf),
        args.title,
        stamp_page_num=not args.no_page_num,
        qc_png_dir=Path(args.qc_dir) if args.qc_dir else None,
    )
    raw_pdf.unlink(missing_ok=True)
