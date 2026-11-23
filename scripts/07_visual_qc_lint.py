#!/usr/bin/env python3
"""
Stage 6（前置）: 确定性视觉/版式 lint (lightingdesign v2.1)

定位：在「读图模型」介入之前，先用脚本把可判定的版式缺陷扫掉，降低视觉 QC 的成本与方差。
覆盖 6 类可脚本化缺陷（对应《Gemini_v2_评审》建议）：
  1) 空白页 / 近空白页（文字 < 10 字符且无图）
  2) 页底大片留白（> 60 mm，末页除外）
  3) 文字出界（超出页面安全边距）
  4) 字体未嵌入（跨机器打开会掉字）
  5) 数字与单位断行（如 "9170" 与 "lm" 分两行）
  6) 段落/图注重复、章节编号不连续、图表编号跳号
  7) 图片/大样过小（可视高度 < 60 mm）或有效分辨率 < 110 dpi
  8) 页码缺失（页脚区域没有页码）
另含：PNG 质检图数量与 PDF 页数一致性、A3 图幅/文本层检查（--a3）。

用法:
  python 07_visual_qc_lint.py --pdf 01_照明设计方案说明书.pdf [--png-dir qc_pngs] [--a3 02_..._A3.pdf] [--out qc_lint_report.txt]
退出码：无 FAIL → 0；有 FAIL → 1（WARN 不阻塞，需人工看）。
"""
import argparse
import json
import re
import sys
from pathlib import Path

import pymupdf as fitz

PT_TO_MM = 25.4 / 72.0
SAFE_MARGIN_MM = 8.0
BOTTOM_BLANK_MM = 60.0
MIN_FIG_HEIGHT_MM = 60.0
MIN_DPI = 110
UNIT_WORDS = ("lm", "lx", "W", "W/m²", "W/m2", "cd/m²", "cd/m2", "K", "mm", "m²", "m2", "%")


def mm(pt):
    return pt * PT_TO_MM


def lint_pdf(pdf_path: Path):
    items = []

    def add(level, name, detail):
        items.append({"level": level, "item": name, "detail": detail})

    doc = fitz.open(pdf_path)
    n = len(doc)
    full_text_pages = []
    fonts = {}
    pages_out, pages_blank, pages_nearblank, pages_bottom = [], [], [], []
    pages_no_pagenum = []
    img_small, img_lowdpi = [], []
    img_total = 0

    for pno, page in enumerate(doc, start=1):
        d = page.get_text("dict")
        blocks = d.get("blocks", [])
        text_chars = 0
        has_img = False
        spans, img_blocks = [], []
        for b in blocks:
            if b.get("type") == 1:
                has_img = True
                img_blocks.append(b)
                continue
            for line in b.get("lines", []):
                for sp in line.get("spans", []):
                    text_chars += len(sp.get("text", "").strip())
                    spans.append(sp)
        full_text_pages.append("".join(sp.get("text", "") for sp in spans))
        try:
            img_total += len(page.get_images(full=False))
        except Exception:
            pass

        if text_chars < 10 and not has_img:
            pages_blank.append(pno)
            continue

        W, H = page.rect.width, page.rect.height
        if spans:
            ymax = max(sp["bbox"][3] for sp in spans)
            blank = mm(H - ymax)
            if text_chars < 40 and blank > 150:
                pages_nearblank.append(pno)
            elif blank > BOTTOM_BLANK_MM and pno < n:
                pages_bottom.append((pno, blank))

        out = False
        for sp in spans:
            x0, y0, x1, y1 = sp["bbox"]
            if x0 < mm_pt(SAFE_MARGIN_MM) - 2 or y0 < mm_pt(SAFE_MARGIN_MM) - 2 \
                    or x1 > W - mm_pt(SAFE_MARGIN_MM) + 2 or y1 > H - mm_pt(SAFE_MARGIN_MM) + 2:
                out = True
                break
        if out:
            pages_out.append(pno)

        try:
            for f in page.get_fonts(full=True):
                ext = (f[1] or "").lower()
                if ext in ("", "n/a", "none"):
                    name = f[3] if len(f) > 3 else "?"
                    fonts.setdefault(name, set()).add(pno)
        except Exception:
            pass

        for b in img_blocks:
            bb = b.get("bbox")
            if not bb:
                continue
            h_mm, w_mm = mm(bb[3] - bb[1]), mm(bb[2] - bb[0])
            if h_mm < MIN_FIG_HEIGHT_MM and w_mm > 40:
                img_small.append((pno, w_mm, h_mm))
            iw, ih = b.get("width", 1), b.get("height", 1)
            if w_mm > 1 and h_mm > 1:
                dpi = max(iw / (w_mm / 25.4), ih / (h_mm / 25.4))
                if dpi < MIN_DPI:
                    img_lowdpi.append((pno, dpi))

        footer = "".join(sp.get("text", "") for sp in spans if sp["bbox"][1] > H - mm_pt(25))
        if not re.search(r"\d", footer):
            pages_no_pagenum.append(pno)
    doc.close()

    size_mb = pdf_path.stat().st_size / 1e6
    add("PASS" if size_mb <= 15 else "FAIL", "报告体积", f"{size_mb:.2f} MB（阈值 15 MB）")
    add("PASS" if img_total >= 2 else "FAIL", "报告图片数", f"{img_total} 张（阈值 2，防纯文本报告）")

    # ---- 页级汇总 ----
    if pages_blank:
        add("FAIL", "空白页", f"{len(pages_blank)} 页：{pages_blank[:12]}")
    else:
        add("PASS", "空白页", "无")
    if pages_nearblank:
        add("FAIL", "近空白页（文字<40字且页底留白>150mm）", f"{len(pages_nearblank)} 页：{pages_nearblank[:12]}")
    if pages_bottom:
        worst = max(pages_bottom, key=lambda x: x[1])
        add("WARN", "页底留白 >60mm", f"{len(pages_bottom)} 页；最严重 p{worst[0]}（{worst[1]:.0f} mm）")
    if pages_out:
        add("FAIL", "文字出界", f"{len(pages_out)} 页：{pages_out[:12]}")
    if fonts:
        detail = "；".join(f"{k}（{len(v)} 页）" for k, v in list(fonts.items())[:6])
        add("WARN", "字体未嵌入", f"{len(fonts)} 种：{detail}")
    else:
        add("PASS", "字体嵌入", "全部字体已嵌入或无需嵌入")
    if pages_no_pagenum:
        add("WARN", "页脚缺页码", f"{len(pages_no_pagenum)}/{n} 页：{pages_no_pagenum[:12]}")
    else:
        add("PASS", "页码", "每页页脚均有数字")
    if img_small:
        add("WARN", "图片/大样偏小", f"{len(img_small)} 处（可视高度<{MIN_FIG_HEIGHT_MM:.0f}mm）：p{img_small[0][0]} 等")
    if img_lowdpi:
        add("WARN", "图片分辨率不足", f"{len(img_lowdpi)} 处（<{MIN_DPI} dpi）：p{img_lowdpi[0][0]} 等")

    text = "\n".join(full_text_pages)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # ---- 文本级 ----
    breaks = []
    for pno, t in enumerate(full_text_pages, start=1):
        ls = [x.strip() for x in t.splitlines() if x.strip()]
        for a, b in zip(ls, ls[1:]):
            if re.fullmatch(r"[\d\.,\s]+", a) and any(b.startswith(u) for u in UNIT_WORDS):
                breaks.append((pno, a, b))
    if breaks:
        add("WARN", "数字/单位断行", f"{len(breaks)} 处，如 p{breaks[0][0]}: '{breaks[0][1]}' + '{breaks[0][2]}'")

    dup = {}
    for ln in lines:
        if len(ln) >= 35:
            dup[ln] = dup.get(ln, 0) + 1
    for ln, c in dup.items():
        if c > 1:
            add("FAIL", "段落重复", f"{c} 次：{ln[:30]}…")

    nums = [int(m.group(1)) for m in (re.match(r"^(\d{1,2})[\.、\s]", ln) for ln in lines) if m]
    nums = [x for x in nums if 1 <= x <= 30]
    if len(nums) >= 3:
        uniq = []
        for x in nums:
            if not uniq or x != uniq[-1]:
                uniq.append(x)
        jumps = [(a, b) for a, b in zip(uniq, uniq[1:]) if b != a + 1 and b != 1]
        if jumps:
            add("WARN", "章节编号不连续", f"{jumps[:3]}")

    for kind in ("图", "表"):
        found = [int(x) for x in re.findall(kind + r"\s*(\d+)", text)]
        seq = []
        for x in found:
            if not seq or x != seq[-1]:
                seq.append(x)
        jumps = [(a, b) for a, b in zip(seq, seq[1:]) if b != a + 1 and b != 1]
        if jumps:
            add("WARN", f"{kind}编号跳号", f"{jumps[:3]}")

    return items


def mm_pt(v):
    return v / PT_TO_MM


def lint_png_dir(png_dir: Path, expected_pages: int):
    items = []
    pngs = sorted(png_dir.glob("*.png"))
    if not pngs:
        return [{"level": "WARN", "item": "质检 PNG", "detail": "目录为空"}]
    if expected_pages and len(pngs) != expected_pages:
        items.append({"level": "WARN", "item": "质检 PNG 页数", "detail": f"{len(pngs)} 张 vs PDF {expected_pages} 页"})
    for p in pngs[:40]:
        try:
            from PIL import Image
            with Image.open(p) as im:
                w, h = im.size
            if w < 800 or h < 1000:
                items.append({"level": "WARN", "item": f"PNG 偏小 {p.name}", "detail": f"{w}×{h}"})
        except Exception:
            items.append({"level": "WARN", "item": f"PNG 无法读取 {p.name}", "detail": ""})
    return items


def lint_a3(a3_pdf: Path):
    items = []
    d = fitz.open(a3_pdf)
    r = d[0].rect
    w, h = mm(r.width), mm(r.height)
    ok = (abs(w - 420) <= 0.5 and abs(h - 297) <= 0.5) or (abs(w - 297) <= 0.5 and abs(h - 420) <= 0.5)
    items.append({"level": "PASS" if ok else "FAIL", "item": "A3 幅面", "detail": f"{w:.1f}×{h:.1f} mm"})
    text = d[0].get_text()
    for k in ("图号", "比例"):
        items.append({"level": "PASS" if k in text else "FAIL", "item": f"A3 文本层 {k}", "detail": "存在" if k in text else "缺失"})
    items.append({"level": "PASS" if "图名" in text else "WARN", "item": "A3 文本层 图名（标签）",
                  "detail": "存在" if "图名" in text else "未用『图名』字样标注（建议补，便于审图）"})
    if not re.search(r"1\s*[:：]\s*\d{2,3}", text):
        items.append({"level": "FAIL", "item": "A3 比例标注", "detail": "未找到 1:XX"})
    try:
        ndraw = len(d[0].get_drawings())
    except Exception:
        ndraw = 0
    items.append({"level": "PASS" if ndraw >= 20 else "FAIL", "item": "A3 图元数量",
                  "detail": f"{ndraw} 个矢量图元（阈值 20，防空白图框）"})
    d.close()
    return items


def main():
    ap = argparse.ArgumentParser(description="Stage 6 前置：确定性视觉/版式 lint")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--png-dir", default="")
    ap.add_argument("--a3", default="")
    ap.add_argument("--out", default="qc_lint_report.txt")
    ap.add_argument("--json-out", default="")
    args = ap.parse_args()

    pdf = Path(args.pdf)
    if not pdf.is_file():
        print(f"[07 lint] 找不到 PDF: {pdf}", file=sys.stderr)
        return 2
    items = lint_pdf(pdf)
    pages = None
    try:
        d = fitz.open(pdf); pages = d.page_count; d.close()
    except Exception:
        pass
    if args.png_dir:
        items += lint_png_dir(Path(args.png_dir), pages)
    if args.a3:
        items += lint_a3(Path(args.a3))

    fails = [i for i in items if i["level"] == "FAIL"]
    warns = [i for i in items if i["level"] == "WARN"]
    summary = f"视觉/版式 lint：{len(items)} 项，FAIL={len(fails)}，WARN={len(warns)}"
    print(summary)
    for i in items:
        print(f"  [{i['level']}] {i['item']}: {i['detail']}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(summary + "\n" + "\n".join(f"[{i['level']}] {i['item']}: {i['detail']}" for i in items),
                   encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps({"summary": summary, "items": items}, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    print(f"结果已写入 {out}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
