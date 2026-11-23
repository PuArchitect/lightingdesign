#!/usr/bin/env python3
"""
Stage 5 备选：把 templates/report_client.html 的 {{占位符}} 用 results/room_lock 等数据填满，
输出可交给 05_build_report_pdf.py（浏览器环境）打印的 report.html。

用法：
  python 05b_fill_report.py --results results.json --room-lock room_lock.json \
      --env env_fingerprint.json --closure closure_audit.json \
      --falsecolor 04_伪彩.png --cove-detail 07_节点.png \
      --out-html report.html

说明：Story 版（tools/report_story_*.py）是主路径；本脚本只服务“有浏览器 + 想用 HTML 模板”的备选路径。
"""
import argparse
import base64
import html
import json
from datetime import date
from pathlib import Path


def esc(v):
    return html.escape(str(v), quote=False)


def img_uri(p: Path | None) -> str:
    if not p or not p.is_file():
        return ""
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"


def rows(cells_list, header=True):
    out = []
    for i, cells in enumerate(cells_list):
        tag = "th" if (header and i == 0) else "td"
        out.append("<tr>" + "".join(f"<{tag}>{esc(c)}</{tag}>" for c in cells) + "</tr>")
    return "".join(out)


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8")) if p and Path(p).is_file() else {}


def main():
    ap = argparse.ArgumentParser(description="填充报告模板占位符（Stage 5 备选）")
    ap.add_argument("--template", default=str(Path(__file__).resolve().parents[1] / "templates" / "report_client.html"))
    ap.add_argument("--results", required=True)
    ap.add_argument("--room-lock", required=True)
    ap.add_argument("--env", default="")
    ap.add_argument("--closure", default="")
    ap.add_argument("--scheme", default="")
    ap.add_argument("--falsecolor", default="")
    ap.add_argument("--cove-detail", default="")
    ap.add_argument("--out-html", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--version", default="v2.3")
    ap.add_argument("--company", default="田野建筑")
    ap.add_argument("--theme", default=str(Path(__file__).resolve().parents[1] / "themes" / "neutral_light.json"))
    args = ap.parse_args()

    res = load(args.results)
    lock = load(args.room_lock)
    env = load(args.env)
    clo = load(args.closure)
    sch = load(args.scheme)

    ps = res.get("power_summary", {})
    wu = res.get("workplane_usable", {})
    dm = lock.get("net_dimensions_mm", {})
    grade = res.get("credibility_grades", {})
    title = args.title or f"{res.get('project_name','')} · {res.get('room_name','')} 照明设计方案"

    fixtures = [["编号", "灯具", "数量/长度", "光通 lm", "功率 W"]]
    for f in res.get("fixtures", []):
        lm = f.get("total_lumens", 0) or 0
        fixtures.append([f.get("code", ""), f.get("name", ""), f.get("quantity_or_length", ""), lm,
                         round(lm / 110.0, 1) if lm else ""])

    illum = [["测面", "平均 lx", "Uo", "点数"],
             ["工作面 0.75 m（可用区）", wu.get("avg_lx", ""), f"{wu.get('uo', 0):.2f}", wu.get("valid_points", "")]]
    wa = res.get("workplane_active")
    if wa:
        illum.append(["工作面 0.75 m（活动区）", wa.get("avg_lx", ""), f"{wa.get('uo', 0):.2f}", wa.get("valid_points", "")])

    scenes = [["场景", "估算 lx"]]
    for s in res.get("scenes", []):
        scenes.append([s.get("name", ""), s.get("estimated_avg_lx", "")])

    layers = [["层", "光源", "作用"]]
    for l in sch.get("layers", []):
        layers.append([l.get("id", "") + " " + l.get("name", ""), l.get("name", ""), l.get("role", "")])

    pending = [["#", "待确认事项"]]
    for i, item in enumerate(res.get("pending_items", []), start=1):
        pending.append([i, item])
    if len(pending) == 1:
        pending.append([1, "无 IES 配光；铜顶/艺术漆反射率待确认；场景值为线性估算，不作为验收依据。"])

    limits = res.get("limitations") or [
        "无 IES，配光 C 级，绝对照度 ±20–30%",
        "无 UGR/眩光实测",
        "场景照度为线性估算",
        "材料反射率未经样板确认",
    ]

    mapping = {
        "project_name": res.get("project_name", ""),
        "room_name": res.get("room_name", ""),
        "formal_title": title,
        "drawing_no": res.get("drawing_no", "L-04"),
        "company": args.company,
        "version": args.version,
        "date": date.today().isoformat(),
        "capability_level": res.get("capability_level", env.get("capability_level", "")),
        "grade_geometry": grade.get("geometry", ""),
        "grade_photometry": grade.get("photometry", ""),
        "grade_material": grade.get("material", ""),
        "net_area_m2": lock.get("net_area_m2", ps.get("room_area_m2", "")),
        "length_mm": dm.get("length", ""),
        "width_mm": dm.get("width", ""),
        "ceiling_height_mm": dm.get("height", ""),
        "workplane_avg_lx": wu.get("avg_lx", ""),
        "total_lumens": ps.get("total_lumens", ""),
        "total_power_w": ps.get("total_power_w", ""),
        "lpd_w_m2": ps.get("lpd_w_m2", ""),
        "led_efficacy_lm_w": ps.get("led_system_efficacy_lm_w", 110),
        "efficacy_grade": ps.get("efficacy_assumption_grade", ""),
        "closure_diff_pct": clo.get("diff_pct", ""),
        "grid_step_m": (res.get("grid_mask") or {}).get("step_m", 0.5),
        "calc_method": (res.get("provenance") or {}).get("physics", "L3 逐点计算"),
        "material_audit_status": "已映射（铜顶/艺术漆待确认）",
        "lighting_strategy_summary": "铜顶灯槽做轮廓，跌级洗墙做环境，射灯做茶几重点，筒灯托工作面。",
        "disclaimer_text": "本方案无 IES 配光，绝对照度不确定度 ±20–30%；T-A 仅作设计目标，不写成施工验收条款。",
        "falsecolor_img": img_uri(Path(args.falsecolor) if args.falsecolor else None),
        "cove_detail_img": img_uri(Path(args.cove_detail) if args.cove_detail else None),
        "fixtures_table_rows": rows(fixtures),
        "illuminance_table_rows": rows(illum),
        "scenes_table_rows": rows(scenes),
        "layers_table_rows": rows(layers),
        "pending_items_rows": rows(pending),
        "limitations_list_items": "".join(f"<li>{esc(x)}</li>" for x in limits),
        "vhi": 200, "vlo": 0,
    }

    tpl = Path(args.template).read_text(encoding="utf-8")
    theme = load(args.theme)
    colors = (theme or {}).get("colors", {})
    if colors and "</head>" in tpl:
        var_css = ":root{--ink:%s;--muted:%s;--line:%s;--bg-soft:%s;--accent:%s;--accent-bg:%s}" % (
            colors.get("ink", "#111827"), colors.get("muted", "#4B5563"),
            colors.get("line", "#D1D5DB"), colors.get("table_head", "#F9FAFB"),
            colors.get("accent", "#B45309"), colors.get("note_bg", "#FFFBEB"))
        tpl = tpl.replace("</head>", f"<style>{var_css}</style></head>", 1)
    # 把同目录 styles.css 内联，保证输出 HTML 自包含（换目录打印也不掉样式）
    css = Path(args.template).parent / "styles.css"
    if css.is_file():
        tpl = tpl.replace('<link rel="stylesheet" href="styles.css" />', f"<style>{css.read_text(encoding='utf-8')}</style>")
    for k, v in mapping.items():
        tpl = tpl.replace("{{" + k + "}}", str(v))

    left = []
    import re
    for m in re.finditer(r"\{\{([^}]+)\}\}", tpl):
        left.append(m.group(1))
    Path(args.out_html).write_text(tpl, encoding="utf-8")
    print(f"[05b] 已填充 -> {args.out_html}；未替换占位符 {len(set(left))} 个")
    if left:
        print("  未替换:", ", ".join(sorted(set(left))[:20]))
    return 0 if not left else 1


if __name__ == "__main__":
    raise SystemExit(main())
