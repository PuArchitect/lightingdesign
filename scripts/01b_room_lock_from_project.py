#!/usr/bin/env python3
"""
Stage 1（推荐）: 由冻结题生成 room_lock.json + 真实平面确认图 (lightingdesign v2.1)

v2.1 新增脚本。与 01_extract_geometry.py 的区别：
  - 不从 bbox 猜房间，而是把「人工已确认的冻结题（project.json）+ 实测几何（canonical）」写成唯一基准；
  - 输出可被 04_render_svg_a3 / 06_preflight_delivery 直接消费的 room_lock（含 zones/openings/ceiling/service_core）；
  - 生成带墙线/门窗/服务核/天花凹槽/尺寸的确认图，供 Stage 1 人工签字。

用法:
  python 01b_room_lock_from_project.py \
    --project project/project_room4_雪茄吧.json \
    --canonical project/整间房间数据.json \
    --out-json room_lock.json --out-png 00_房间边界确认图.png
"""
import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _font(size):
    for f in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _rect_mm(r):
    """[x0,y0,x1,y1] m -> [x0,y0,x1,y1] mm"""
    return [round(float(v) * 1000, 1) for v in r]


def build_lock(project: dict, canonical: dict, project_path: Path) -> dict:
    sc = project["scope"]
    b = sc["bbox_m"]
    bounds_mm = {"x_min": b["x0"] * 1000, "x_max": b["x1"] * 1000,
                 "y_min": b["y0"] * 1000, "y_max": b["y1"] * 1000,
                 "z_min": b["z0"] * 1000, "z_max": b["z1"] * 1000}
    W = round((b["x1"] - b["x0"]) * 1000, 1)
    D = round((b["y1"] - b["y0"]) * 1000, 1)
    H = round((b["z1"] - b["z0"]) * 1000, 1)
    area_measured = round(W * D / 1e6, 2)
    area_declared = float(sc["area_design_m2"])
    area_dev_pct = round(abs(area_measured - area_declared) / area_declared * 100, 2) if area_declared else 0.0

    # v2.2.3：canonical 与冻结题的 bbox / 面积必须互相校验，冲突写入 discrepancies
    discrepancies = []
    canon_room = canonical.get("room", {}) or {}
    canon_bbox = canon_room.get("bbox_m") or {}
    for k in ("x0", "x1", "y0", "y1"):
        if k in canon_bbox and abs(float(canon_bbox[k]) - float(b[k])) > 0.005:
            discrepancies.append(f"bbox.{k} 冻结题={b[k]} m，实测={canon_bbox[k]} m（差 >5 mm）")
    canon_area = canon_room.get("area_m2")
    if canon_area is not None and abs(float(canon_area) - area_declared) / area_declared > 0.01:
        discrepancies.append(f"面积 冻结题={area_declared} m²，实测几何={canon_area} m²（差 >1%）")


    zones = []
    for z in sc.get("zones", []):
        zones.append({"id": z["id"], "name": z["name"],
                      "rect_mm": _rect_mm([z["x"][0], z["y"][0], z["x"][1], z["y"][1]]),
                      "role": z.get("role", ""), "ceiling": z.get("ceiling", "")})

    openings = []
    for op in canonical.get("openings", []):
        openings.append({"id": op["id"], "type": op["type"], "rect_mm": _rect_mm(op["rect"]),
                         "z_range_m": op.get("z_range_m"), "block": op.get("block", ""), "note": op.get("note", "")})

    ceil = canonical.get("ceiling", {}) or {}
    recess = ceil.get("recess") or {}
    copper = ceil.get("copper_plate") or {}
    if not recess or not copper:
        raise ValueError("canonical 缺少 ceiling.recess 或 ceiling.copper_plate，无法生成 room_lock")
    ceiling = {
        "soffit_z_m": ceil.get("soffit_z"),
        "soffit_z_range_m": ceil.get("soffit_z"),
        "recess": {
            "rect_mm": _rect_mm(recess["rect"]),
            "bottom_z_m": recess["bottom_z"],
            "top_z_m": recess["top_z"],
        },
        "copper_plate": {
            "rect_mm": _rect_mm(copper["rect"]),
            "z_m": copper["z"],
            "material": copper.get("material", ""),
        },
    }

    service_core = None
    for z in sc.get("zones", []):
        if z["id"] == "Z3" or "卫生间" in z.get("name", ""):
            service_core = {"rect_mm": _rect_mm([z["x"][0], z["y"][0], z["x"][1], z["y"][1]]),
                            "note": z.get("role", "统计剔除，建模保留")}
            break

    warnings = []
    if area_dev_pct > 1.0:
        warnings.append(f"实测矩形面积 {area_measured} m² 与冻结题 {area_declared} m² 偏差 {area_dev_pct}%（>1%，需说明 L 形/扣减）")
    for x in discrepancies:
        warnings.append("几何冲突：" + x)
    # 门窗是否落在墙线上（粗略）
    for op in openings:
        r = op["rect_mm"]
        on_wall = (abs(r[1] - bounds_mm["y_min"]) < 200 or abs(r[3] - bounds_mm["y_max"]) < 200
                   or abs(r[0] - bounds_mm["x_min"]) < 200 or abs(r[2] - bounds_mm["x_max"]) < 200)
        if not on_wall:
            warnings.append(f"{op['id']} 未落在房间四边 200 mm 内，请核对门窗位置")

    return {
        "schema_version": "2.1",
        "room_name": project["project"]["name"].split("·")[-1].strip() if "·" in project["project"]["name"] else sc["room_id"],
        "room_id": sc["room_id"],
        "source_model": next((e["file"] for e in project.get("evidence", []) if "3dm" in e["file"]), ""),
        "source_project": str(project_path),
        "source_hash": hashlib.sha256(project_path.read_bytes()).hexdigest()[:16],
        "cross_evidence": [e["item"] for e in project.get("evidence", [])],
        "bounds_mm": bounds_mm,
        "net_dimensions_mm": {"length": W, "width": D, "height": H},
        "net_area_m2": area_measured,
        "area_measured_m2": area_measured,
        "area_declared_m2": area_declared,
        "area_deviation_pct": area_dev_pct,
        "area_method": "finished-wall bbox 实算（W×D）；统计面积剔除服务核",
        "discrepancies_to_confirm": discrepancies,
        "scope": sc["extent"],
        "zones": zones,
        "openings": openings,
        "ceiling": ceiling,
        "service_core": service_core,
        "signoff": {"confirmed_by": sc.get("confirmed_by", ""), "confirmed_at": sc.get("confirmed_at", ""),
                    "date": date.today().isoformat()},
        "warnings": warnings,
        "confidence": "B+（冻结题 + 3dm 实测；待现场复尺）",
    }


def render_plan(lock: dict, canonical: dict, out_png: Path):
    W = lock["net_dimensions_mm"]["length"]; D = lock["net_dimensions_mm"]["width"]
    x0 = lock["bounds_mm"]["x_min"]; y0 = lock["bounds_mm"]["y_min"]
    margin, top = 90, 90
    scale = min((1000 - 2 * margin) / W, (760 - top - 120) / D)
    w, h = W * scale, D * scale
    img = Image.new("RGB", (1000, 760), "white")
    d = ImageDraw.Draw(img)
    f_title, f_mid, f_sm = _font(24), _font(16), _font(13)

    def P(x, y):  # mm -> px（y 向上）
        return (margin + (x - x0) * scale, top + (D - (y - y0)) * scale)

    # 房间外框（墙）
    d.rectangle([margin, top, margin + w, top + h], outline="#111827", width=5)
    d.text((margin, 30), f"房间边界确认图 · {lock['room_name']}", fill="#111827", font=f_title)
    d.text((margin, 62), f"整间 {W/1000:.2f} × {D/1000:.2f} m｜{lock['net_area_m2']} m²｜净高 {lock['net_dimensions_mm']['height']/1000:.2f} m｜确认 {lock['signoff']['confirmed_at']}",
           fill="#374151", font=f_mid)

    # 分区
    colors = {"Z1": "#F3F4F6", "Z2": "#E0E7FF", "Z3": "#D1D5DB"}
    for z in lock["zones"]:
        r = z["rect_mm"]
        a, b = P(r[0], r[1]), P(r[2], r[3])
        d.rectangle([a[0], b[1], b[0], a[1]], fill=colors.get(z["id"]), outline=None)
        d.text((a[0] + 6, b[1] + 6), z["name"], fill="#4B5563", font=f_sm)

    # 服务核斜线
    if lock.get("service_core"):
        r = lock["service_core"]["rect_mm"]
        a, b = P(r[0], r[1]), P(r[2], r[3])
        step = 12
        xx = a[0] - (b[1] - a[1])
        while xx < b[0]:
            d.line([(max(a[0], xx), b[1]), (min(b[0], xx + (b[1] - a[1])), a[1])], fill="#9CA3AF", width=1)
            xx += step
        d.rectangle([a[0], b[1], b[0], a[1]], outline="#6B7280", width=2)

    # 天花凹槽（虚线）与铜顶
    def dashed_rect(r, color, dash=8):
        a, b = P(r[0], r[1]), P(r[2], r[3])
        pts = [(a[0], a[1]), (b[0], a[1]), (b[0], b[1]), (a[0], b[1]), (a[0], a[1])]
        for i in range(len(pts) - 1):
            (x1, y1), (x2, y2) = pts[i], pts[i + 1]
            ln = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            n = max(1, int(ln // dash))
            for k in range(n):
                t1, t2 = k / n, (k + 0.55) / n
                d.line([(x1 + (x2 - x1) * t1, y1 + (y2 - y1) * t1),
                        (x1 + (x2 - x1) * t2, y1 + (y2 - y1) * t2)], fill=color, width=2)

    dashed_rect(lock["ceiling"]["recess"]["rect_mm"], "#B45309")
    dashed_rect(lock["ceiling"]["copper_plate"]["rect_mm"], "#92400E")

    # 门窗
    for op in lock.get("openings", []):
        r = op["rect_mm"]
        if op["type"] == "门":
            a, b = P(r[0], r[1]), P(r[2], r[3])
            d.line([a, b], fill="white", width=6)  # 打断墙线
            d.line([a, b], fill="#DC2626", width=2)
            d.arc([a[0], a[1] - (b[0] - a[0]), a[0] + (b[0] - a[0]) * 2, a[1] + (b[0] - a[0])],
                  start=270, end=360, fill="#DC2626", width=1)
            d.text((a[0] + 2, a[1] + 4), op["id"], fill="#B91C1C", font=f_sm)
        else:
            a, b = P(r[0], r[1]), P(r[2], r[3])
            d.line([a, b], fill="white", width=6)
            for off in (-3, 3):
                d.line([(a[0], a[1] + off), (b[0], b[1] + off)], fill="#2563EB", width=1)
            d.text((a[0] + 2, a[1] + 5), op["id"], fill="#1D4ED8", font=f_sm)

    # 尺寸标注
    d.line([(margin, top + h + 24), (margin + w, top + h + 24)], fill="#111827", width=1)
    d.text((margin + w / 2 - 40, top + h + 30), f"{W:.0f} mm", fill="#111827", font=f_mid)
    d.line([(margin - 24, top), (margin - 24, top + h)], fill="#111827", width=1)
    d.text((margin - 80, top + h / 2), f"{D:.0f}", fill="#111827", font=f_mid)

    y = top + h + 70
    for wmsg in lock.get("warnings", [])[:3]:
        d.text((margin, y), "⚠ " + wmsg[:60], fill="#92400E", font=f_sm)
        y += 20
    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png)


def render_plan_v2(lock: dict, canonical: dict, out_png: Path):
    """v2.2.3：先填分区、后画墙线；门窗内偏、图例区分凹槽/铜顶。"""
    W = lock["net_dimensions_mm"]["length"]
    D = lock["net_dimensions_mm"]["width"]
    x0, y0 = lock["bounds_mm"]["x_min"], lock["bounds_mm"]["y_min"]
    CW, CH = 1400, 1000
    margin, top = 110, 120
    scale = min((CW - 2 * margin) / W, 650 / D)
    w, h = W * scale, D * scale
    img = Image.new("RGB", (CW, CH), "white")
    d = ImageDraw.Draw(img)
    f_title, f_mid, f_sm, f_tiny = _font(34), _font(21), _font(17), _font(14)

    def P(x, y):
        return (margin + (x - x0) * scale, top + (D - (y - y0)) * scale)

    # 1) 分区填充
    colors = {"Z1": "#F3F4F6", "Z2": "#E0E7FF", "Z3": "#D1D5DB"}
    for z in lock.get("zones", []):
        r = z["rect_mm"]
        a, b = P(r[0], r[1]), P(r[2], r[3])
        d.rectangle([a[0], b[1], b[0], a[1]], fill=colors.get(z["id"], "#F9FAFB"))
        d.text((a[0] + 8, b[1] + 8), z["name"], fill="#4B5563", font=f_sm)

    # 2) 服务核斜线
    if lock.get("service_core"):
        r = lock["service_core"]["rect_mm"]
        a, b = P(r[0], r[1]), P(r[2], r[3])
        xx = a[0] - (b[1] - a[1])
        while xx < b[0]:
            d.line([(max(a[0], xx), b[1]), (min(b[0], xx + (b[1] - a[1])), a[1])], fill="#9CA3AF", width=1)
            xx += 12
        d.rectangle([a[0], b[1], b[0], a[1]], outline="#6B7280", width=2)

    # 3) 天花凹槽（橙虚线）与铜顶（铜色双点划线）
    def dashed(r, color, dash=10, width=2):
        a, b = P(r[0], r[1]), P(r[2], r[3])
        pts = [(a[0], a[1]), (b[0], a[1]), (b[0], b[1]), (a[0], b[1]), (a[0], a[1])]
        for i in range(len(pts) - 1):
            (x1, y1), (x2, y2) = pts[i], pts[i + 1]
            ln = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            n = max(1, int(ln // dash))
            for k in range(n):
                t1, t2 = k / n, (k + 0.55) / n
                d.line([(x1 + (x2 - x1) * t1, y1 + (y2 - y1) * t1),
                        (x1 + (x2 - x1) * t2, y1 + (y2 - y1) * t2)], fill=color, width=width)

    dashed(lock["ceiling"]["recess"]["rect_mm"], "#EA8C1B", 10, 3)
    dashed(lock["ceiling"]["copper_plate"]["rect_mm"], "#8B4A20", 6, 2)

    # 4) 墙线（最后画，避免被填充覆盖）
    d.rectangle([margin - 4, top - 4, margin + w + 4, top + h + 4], outline="#0F172A", width=9)

    # 5) 门窗（打断墙线 + 内偏符号）
    for op in lock.get("openings", []):
        r = op["rect_mm"]
        d_b = abs(r[3] - lock["bounds_mm"]["y_min"])
        d_t = abs(r[1] - lock["bounds_mm"]["y_max"])
        d_l = abs(r[0] - lock["bounds_mm"]["x_min"])
        d_r = abs(r[2] - lock["bounds_mm"]["x_max"])
        side = min(("bottom", d_b), ("top", d_t), ("left", d_l), ("right", d_r), key=lambda t: t[1])[0]
        if side in ("bottom", "top"):
            x1p = P(r[0], 0)[0]; x2p = P(r[2], 0)[0]
            wall_y = top + h if side == "bottom" else top
            d.line([(x1p, wall_y), (x2p, wall_y)], fill="white", width=14)
            if op["type"] == "门":
                ln = abs(x2p - x1p)
                hinge = (x1p, wall_y)
                if side == "bottom":
                    d.line([hinge, (x1p, wall_y - ln)], fill="#DC2626", width=3)
                    d.arc([x1p - ln, wall_y - ln, x1p + ln, wall_y + ln], start=270, end=360, fill="#DC2626", width=2)
                    d.text((x1p + 6, wall_y - ln - 26), op["id"], fill="#B91C1C", font=f_sm)
                else:
                    d.line([hinge, (x1p, wall_y + ln)], fill="#DC2626", width=3)
                    d.arc([x1p - ln, wall_y - ln, x1p + ln, wall_y + ln], start=0, end=90, fill="#DC2626", width=2)
                    d.text((x1p + 6, wall_y + ln + 8), op["id"], fill="#B91C1C", font=f_sm)
            else:
                off = 6 if side == "top" else -6
                for o in (off, off + (5 if side == "top" else -5)):
                    d.line([(x1p, wall_y + o), (x2p, wall_y + o)], fill="#2563EB", width=2)
                for k in (1, 2, 3):
                    mx = x1p + (x2p - x1p) * k / 4
                    d.line([(mx, wall_y + 2), (mx, wall_y + 13) if side == "top" else (mx, wall_y - 13)], fill="#2563EB", width=2)
                label = op["id"] + "  4×400×1200（z 0.82–2.08）"
                d.text((x1p, wall_y + 30 if side == "top" else wall_y - 46), label, fill="#1D4ED8", font=f_tiny)

    # 6) 尺寸
    yb = top + h + 55
    d.line([(margin, yb), (margin + w, yb)], fill="#111827", width=2)
    for xx in (margin, margin + w):
        d.line([(xx, yb - 8), (xx, yb + 8)], fill="#111827", width=2)
    d.text((margin + w / 2 - 70, yb + 10), f"{W:.0f} mm", fill="#111827", font=f_mid)
    xl = margin - 55
    d.line([(xl, top), (xl, top + h)], fill="#111827", width=2)
    for yy in (top, top + h):
        d.line([(xl - 8, yy), (xl + 8, yy)], fill="#111827", width=2)
    d.text((8, top + h / 2), f"{D:.0f} mm", fill="#111827", font=f_mid)

    # 7) 图例
    lx, ly = margin + w - 360, top + h + 95
    d.rectangle([lx, ly, lx + 350, ly + 120], outline="#9CA3AF", width=1, fill="white")
    d.text((lx + 10, ly + 8), "图例", fill="#111827", font=f_sm)
    d.line([(lx + 10, ly + 38), (lx + 50, ly + 38)], fill="#EA8C1B", width=3)
    d.text((lx + 60, ly + 30), "天花凹槽 2.74–3.04 m", fill="#4B5563", font=f_tiny)
    d.line([(lx + 10, ly + 62), (lx + 50, ly + 62)], fill="#8B4A20", width=2)
    d.text((lx + 60, ly + 54), "铜顶顶板 3.04 m", fill="#4B5563", font=f_tiny)
    d.line([(lx + 10, ly + 86), (lx + 50, ly + 86)], fill="#0F172A", width=8)
    d.text((lx + 60, ly + 78), "完成面墙", fill="#4B5563", font=f_tiny)
    d.line([(lx + 10, ly + 108), (lx + 50, ly + 108)], fill="#DC2626", width=3)
    d.text((lx + 60, ly + 100), "门（内开 90°）", fill="#4B5563", font=f_tiny)

    # 8) 标题与告警
    d.text((margin, 30), f"房间边界确认图 · {lock['room_name']}", fill="#111827", font=f_title)
    d.text((margin, 78), f"整间 {W/1000:.2f} × {D/1000:.2f} m｜实测 {lock['net_area_m2']} m²"
                        f"（冻结 {lock.get('area_declared_m2','?')}，偏差 {lock.get('area_deviation_pct','?')}%）"
                        f"｜净高 {lock['net_dimensions_mm']['height']/1000:.2f} m", fill="#374151", font=f_mid)
    d.text((margin + w - 120, 78), "单位：mm", fill="#6B7280", font=f_tiny)
    y = top + h + 95
    for wmsg in lock.get("warnings", [])[:2]:
        d.text((margin, y), "⚠ " + wmsg[:55], fill="#92400E", font=f_tiny)
        y += 22

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Stage 1：冻结题 -> room_lock + 真实确认图 (v2.1)")
    ap.add_argument("--project", required=True)
    ap.add_argument("--canonical", required=True)
    ap.add_argument("--out-json", default="room_lock.json")
    ap.add_argument("--out-png", default="00_房间边界确认图.png")
    args = ap.parse_args()
    pp = Path(args.project)
    project = json.loads(pp.read_text(encoding="utf-8"))
    canonical = json.loads(Path(args.canonical).read_text(encoding="utf-8"))
    lock = build_lock(project, canonical, pp)
    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps(lock, ensure_ascii=False, indent=2), encoding="utf-8")
    render_plan_v2(lock, canonical, Path(args.out_png))
    print(f"[Stage 1b] room_lock: {lock['room_name']} {lock['net_area_m2']} m² -> {args.out_json}")
    for w in lock["warnings"]:
        print("  [WARN]", w)
