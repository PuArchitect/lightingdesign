#!/usr/bin/env python3
"""
Stage 1（备选）: 3dm 几何提取与房间边界锁定 (lightingdesign v2.1)
v2.1 修改（相对 v2.0）：
  1) 只对可求 bbox 的实体类型取包围盒（Text/Annotation/InstanceReference/NurbsCurve 等跳过，v2.0 在 Text 上直接崩溃）；
  2) 新增 --roi（x0 x1 y0 y1，mm）——无冻结题时必填，防止拿整模型 bbox 当房间；
  3) 新增 --layers 图层白名单（子串匹配，如 2-INTR::墙面,1-ARCH::空间::墙）；
  4) 尺寸异常过滤：bbox 对角线超过 ROI 对角线 1.3 倍的块/大对象丢弃并记 warning；
  5) 输出 warnings 与 confidence，提醒「bbox 方法不能表达 L 形/服务核/门窗」。
注意：有冻结题时优先用 01b_room_lock_from_project.py，不要用本脚本猜房间。
"""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SOLID_TYPES = {"Brep", "Extrusion", "Mesh", "Surface"}


def _font(size=18):
    for f in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _bbox(geom):
    try:
        b = geom.GetBoundingBox()
        if b.IsValid:
            return (b.Min.X, b.Min.Y, b.Min.Z, b.Max.X, b.Max.Y, b.Max.Z)
    except Exception:
        return None
    return None


def extract(model_path: Path, roi, layers, allow_whole=False):
    import rhino3dm  # type: ignore
    model = rhino3dm.File3dm.Read(str(model_path))
    if model is None:
        raise RuntimeError(f"无法读取 3dm: {model_path}")
    names = {l.Index: l.FullPath for l in model.Layers}
    if roi is None and not allow_whole:
        raise ValueError("Stage 1 门禁：无冻结题时必须提供 --roi（x0 x1 y0 y1, mm）；"
                         "确认要用整模型 bbox 请显式加 --allow-whole-model。")
    if roi:
        x0, x1, y0, y1 = roi
        roi_diag = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    else:
        roi_diag = None

    xs, ys, zs, used, skipped, warnings = [], [], [], set(), {}, []
    for ob in model.Objects:
        g = ob.Geometry
        t = type(g).__name__
        if t not in SOLID_TYPES:
            skipped[t] = skipped.get(t, 0) + 1
            continue
        layer = names.get(ob.Attributes.LayerIndex, "")
        if layers and not any(k in layer for k in layers):
            continue
        bb = _bbox(g)
        if not bb:
            skipped["no_bbox"] = skipped.get("no_bbox", 0) + 1
            continue
        cx, cy = (bb[0] + bb[3]) / 2, (bb[1] + bb[4]) / 2
        if roi and not (x0 <= cx <= x1 and y0 <= cy <= y1):
            continue
        diag = ((bb[3] - bb[0]) ** 2 + (bb[4] - bb[1]) ** 2) ** 0.5
        if roi_diag and diag > roi_diag * 1.3:
            warnings.append(f"丢弃超大对象（对角线 {diag:.0f} mm > ROI 1.3 倍）: {layer} {t}")
            continue
        xs += [bb[0], bb[3]]; ys += [bb[1], bb[4]]; zs += [bb[2], bb[5]]
        used.add(layer)

    if not xs:
        raise RuntimeError("未提取到有效实体；请检查 --roi / --layers / 单位（mm）。")
    W = round(max(xs) - min(xs), 1); D = round(max(ys) - min(ys), 1); H = round(max(zs) - min(zs), 1)
    if roi and (abs(min(xs) - x0) < 50 or abs(max(xs) - x1) < 50 or abs(min(ys) - y0) < 50 or abs(max(ys) - y1) < 50):
        warnings.append("bbox 贴住 ROI 边界：可能包含相邻空间/天花整片 Brep，面积不可直接采用；有冻结题时请改用 01b。")
    if H > 4000:
        warnings.append(f"bbox 高度 {H:.0f} mm 可能包含结构楼板；净高需从天花面单独量取。")
    return {
        "bounds_mm": {"x_min": round(min(xs), 1), "x_max": round(max(xs), 1),
                      "y_min": round(min(ys), 1), "y_max": round(max(ys), 1),
                      "z_min": round(min(zs), 1), "z_max": round(max(zs), 1)},
        "net_dimensions_mm": {"length": W, "width": D, "height": H},
        "net_area_m2": round(W * D / 1e6, 2),
        "detected_layers": sorted(used),
        "skipped_types": skipped,
        "warnings": warnings,
        "confidence": "C（bbox 近似；L 形/服务核/门窗不可表达，需人工确认）",
    }


def render_preview(lock: dict, out_png: Path):
    img = Image.new("RGB", (1000, 760), "white")
    d = ImageDraw.Draw(img)
    b = lock["bounds_mm"]; dm = lock["net_dimensions_mm"]
    f_big, f_mid, f_sm = _font(24), _font(18), _font(15)
    d.text((40, 30), f"ROOM LOCK（bbox 近似）· {lock['room_name']}", fill="#111827", font=f_big)
    d.text((40, 62), f"Area {lock['net_area_m2']} m² | W {dm['length']} × D {dm['width']} mm | H {dm['height']} mm",
           fill="#374151", font=f_mid)
    box = [120, 130, 620, 560]
    d.rectangle(box, outline="#1F2937", width=4)
    d.text((300, 580), f"X {b['x_min']:.0f} ~ {b['x_max']:.0f} mm", fill="#B91C1C", font=f_mid)
    d.text((660, 330), f"Y {b['y_min']:.0f} ~ {b['y_max']:.0f} mm", fill="#B91C1C", font=f_mid)
    y = 620
    for w in lock.get("warnings", [])[:4]:
        d.text((40, y), "⚠ " + w[:60], fill="#92400E", font=f_sm)
        y += 24
    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png)


def lock_room(model, room, evidence, out_json, out_png, roi, layers, discrepancies=None, allow_whole=False):
    if len(evidence) < 2:
        raise ValueError("Stage 1 门禁：至少 2 条交叉证据。")
    geom = extract(Path(model), roi, layers, allow_whole)
    data = {
        "schema_version": "2.1",
        "room_name": room,
        "source_model": str(model),
        "cross_evidence": evidence,
        "discrepancies_to_confirm": discrepancies or [],
        **geom,
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    render_preview(data, out_png)
    print(f"[Stage 1] room_lock: {room} {geom['net_area_m2']} m² -> {out_json}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Stage 1（备选）3dm 几何提取与房间边界锁定 v2.1")
    ap.add_argument("--model", required=True)
    ap.add_argument("--room", required=True)
    ap.add_argument("--evidence", nargs="+", required=True)
    ap.add_argument("--roi", nargs=4, type=float, metavar=("X0", "X1", "Y0", "Y1"))
    ap.add_argument("--layers", nargs="+", default=[])
    ap.add_argument("--allow-whole-model", action="store_true")
    ap.add_argument("--out-json", default="room_lock.json")
    ap.add_argument("--out-png", default="00_房间边界确认图.png")
    args = ap.parse_args()
    lock_room(args.model, args.room, args.evidence, Path(args.out_json), Path(args.out_png),
              args.roi, args.layers, allow_whole=args.allow_whole_model)
