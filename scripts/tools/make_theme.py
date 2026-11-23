#!/usr/bin/env python3
"""
从项目调性生成报告主题（不预设色板）。

用法示例：
  # 业主 CI 主色是墨绿，浅色封面
  python make_theme.py --base neutral_light --accent "#0F766E" --cover-style light \
      --label "雪茄吧 · 墨绿" --out themes/project_xxx.json

  # 深色奢华，但强调色换成酒红
  python make_theme.py --base cigar_dark --accent "#7F1D1D" --cover-style dark \
      --label "威士忌吧 · 酒红" --out themes/project_yyy.json

  # 只改字体
  python make_theme.py --base warm_minimal --font "Source Han Serif SC" --out themes/project_zzz.json
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
THEMES = ROOT / "themes"


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb2hex(rgb):
    return "#" + "".join(f"{max(0, min(255, int(round(v)))):02X}" for v in rgb)


def mix(a, b, t):
    ra, rb = hex2rgb(a), hex2rgb(b)
    return rgb2hex(tuple(ra[i] * (1 - t) + rb[i] * t for i in range(3)))


def darken(h, t=0.18):
    return mix(h, "#000000", t)


def lighten(h, t=0.90):
    return mix(h, "#FFFFFF", t)


def main():
    ap = argparse.ArgumentParser(description="按项目调性生成报告主题")
    ap.add_argument("--base", default="neutral_light", choices=["neutral_light", "cigar_dark", "warm_minimal"])
    ap.add_argument("--accent", default="", help="强调色，如 #0F766E；不填则用 base 的")
    ap.add_argument("--ink", default="", help="正文色；不填则用 base 的")
    ap.add_argument("--bg", default="", help="页面底色；不填则用 base 的")
    ap.add_argument("--cover-style", default="", choices=["light", "dark", "same"])
    ap.add_argument("--font", default="", help="正文字体，如 Source Han Serif SC")
    ap.add_argument("--display-font", default="", help="标题字体；默认同正文")
    ap.add_argument("--label", default="项目自定义主题")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    theme = json.loads((THEMES / f"{args.base}.json").read_text(encoding="utf-8"))
    c = theme["colors"]
    if args.accent:
        c["accent"] = args.accent
        c["accent_dark"] = darken(args.accent, 0.18)
        c["table_head"] = lighten(args.accent, 0.92)
        c["table_head_ink"] = darken(args.accent, 0.55)
        c["note_bg"] = lighten(args.accent, 0.94)
        c["line"] = lighten(args.accent, 0.84)
        c["line_strong"] = lighten(args.accent, 0.70)
        c["rh_line"] = lighten(args.accent, 0.85)
    if args.ink:
        c["ink"] = args.ink
        c["text_mid"] = mix(args.ink, "#FFFFFF", 0.15)
        c["text_soft"] = mix(args.ink, "#FFFFFF", 0.28)
    if args.bg:
        c["bg"] = args.bg
    style = args.cover_style or "same"
    if style == "light":
        c["cover_bg"], c["cover_title"], c["cover_text"] = c["bg"], c["ink"], c["text_soft"]
        c["cover_kicker"], c["cover_meta"], c["cover_en"] = c["accent"], c["muted"], c["muted"]
        c["cover_border"], c["cover_border2"] = c["line"], c["table_head"]
    elif style == "dark":
        c["cover_bg"] = c["ink"] if args.base != "cigar_dark" else c["cover_bg"]
        c["cover_title"] = "#F9FAFB"
        c["cover_text"] = "#E5E7EB"
        c["cover_kicker"] = c["accent"]
        c["cover_meta"], c["cover_en"] = "#D1D5DB", "#9CA3AF"
        c["cover_border"], c["cover_border2"] = c["line_strong"], c["line"]
    if args.font:
        theme.setdefault("fonts", {})["body"] = args.font
        theme["fonts"]["display"] = args.display_font or args.font
    theme["id"] = Path(args.out).stem
    theme["label"] = args.label
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(theme, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[make_theme] {args.out} （base={args.base}, accent={c['accent']}, cover={style}）")


if __name__ == "__main__":
    main()
