#!/usr/bin/env python3
"""
tools/svg_to_a3_pdf.py (v2.1 新增)
把 04 生成的 A3 SVG 打印成 420×297 mm 的 PDF。
优先级：cairosvg（若已安装）→ Chrome/Edge 无头打印（@page 420mm×297mm）。
输出后校验物理幅面（±0.5 mm），不通过则报错。
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf as fitz

PT_TO_MM = 25.4 / 72.0
BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]


def find_browser():
    for c in (shutil.which("chrome"), shutil.which("msedge"), shutil.which("google-chrome")):
        if c:
            return c
    for p in BROWSERS:
        if Path(p).is_file():
            return p
    return None


def svg_via_pymupdf(svg_path: Path, out_pdf: Path) -> bool:
    """首选：PyMuPDF 直接解析 SVG 并转 PDF（矢量、文本可检索、不需要浏览器）。"""
    try:
        d = fitz.open(str(svg_path))
        if d.page_count < 1:
            return False
        pdf_bytes = d.convert_to_pdf()
        d.close()
        out_pdf.write_bytes(pdf_bytes)
        return out_pdf.is_file() and out_pdf.stat().st_size > 0
    except Exception as e:
        print(f"[svg_to_a3_pdf] pymupdf 转换失败: {e}")
        return False


def svg_via_cairosvg(svg_path: Path, out_pdf: Path) -> bool:
    try:
        import cairosvg  # type: ignore
    except Exception:
        return False
    cairosvg.svg2pdf(url=str(svg_path), write_to=str(out_pdf))
    return out_pdf.is_file() and out_pdf.stat().st_size > 0


def svg_via_browser(svg_path: Path, out_pdf: Path, browser: str) -> bool:
    # 优先写在输出目录（避免受限机器上的系统临时目录不可写）
    html = out_pdf.parent / "_a3_print.html"
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    svg_text = svg_path.read_text(encoding="utf-8")
    html.write_text(f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
@page {{ size: 420mm 297mm; margin: 0; }}
html,body {{ margin:0; padding:0; }}
svg {{ display:block; width:420mm; height:297mm; }}
</style></head><body>{svg_text}</body></html>""", encoding="utf-8")
    cmd = [browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
           f"--print-to-pdf={out_pdf.resolve()}", html.resolve().as_uri()]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    try:
        html.unlink()
    except Exception:
        pass
    return r.returncode == 0 and out_pdf.is_file() and out_pdf.stat().st_size > 0


def check_a3(pdf_path: Path) -> bool:
    d = fitz.open(pdf_path)
    r = d[0].rect
    w = r.width * PT_TO_MM
    h = r.height * PT_TO_MM
    d.close()
    landscape = abs(w - 420.0) <= 0.5 and abs(h - 297.0) <= 0.5
    portrait = abs(w - 297.0) <= 0.5 and abs(h - 420.0) <= 0.5
    ok = landscape or portrait
    print(f"[svg_to_a3_pdf] 页面 {w:.2f} × {h:.2f} mm -> {'PASS' if ok else 'FAIL（要求 420×297 ±0.5，允许旋转）'}")
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="SVG -> A3 PDF (420×297 mm)")
    ap.add_argument("--svg", required=True)
    ap.add_argument("--out-pdf", required=True)
    ap.add_argument("--browser", default="")
    args = ap.parse_args()
    svg_p, out_p = Path(args.svg), Path(args.out_pdf)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    ok = svg_via_pymupdf(svg_p, out_p)
    if not ok:
        ok = svg_via_cairosvg(svg_p, out_p)
    if not ok:
        browser = args.browser or find_browser()
        if not browser:
            print("[svg_to_a3_pdf] 未找到 cairosvg / Chrome / Edge，无法转换", file=sys.stderr)
            sys.exit(2)
        ok = svg_via_browser(svg_p, out_p, browser)
    if not ok:
        print("[svg_to_a3_pdf] 转换失败", file=sys.stderr)
        sys.exit(1)
    sys.exit(0 if check_a3(out_p) else 1)
