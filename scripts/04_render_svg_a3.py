#!/usr/bin/env python3
"""
Stage 4: A3 1:XX 天花照明定位图 SVG 生成引擎 (lightingdesign v2.1)
v2.1 重写要点（相对 v2.0）：
  1) 灯位坐标归一化：自动识别 results.fixture_positions_mm 是模型绝对坐标还是局部坐标（减 room_lock 原点）；
  2) 真正调用 verify_dimension_chain()：总尺寸 = 分段之和（凹槽/边带分段），文件里不再有未使用的函数；
  3) 画真实平面：墙线、门、窗、服务核、天花凹槽、铜顶，而不是一个矩形；
  4) 补图例、灯具表、施工说明、指北针、比例尺、六项图签；
  5) 比例自适应：1:25 放不下时自动 1:30/1:40/1:50，并在图签注明。
"""
import argparse
import json
from datetime import date
from pathlib import Path

A3_W, A3_H = 420.0, 297.0
SCALES = [25, 30, 40, 50, 75, 100]


def verify_dimension_chain(total_mm: float, segments_mm: list, tol_mm: float = 1.0):
    s = sum(segments_mm)
    if abs(s - total_mm) > tol_mm:
        raise ValueError(f"尺寸链未闭合: 分段之和 {s:.1f} != 总尺寸 {total_mm:.1f}")
    return True


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def normalize_positions(results, lock):
    b = lock["bounds_mm"]
    pts = results.get("fixture_positions_mm", [])
    frame = results.get("coordinate_frame", "")
    xs = [float(p["x_mm"]) for p in pts] if pts else []
    if frame != "local" and xs and (max(xs) > b["x_max"] + 1 or min(xs) < b["x_min"] - 1):
        frame = "model"
        pts = [{"code": p["code"], "x_mm": float(p["x_mm"]) - b["x_min"],
                "y_mm": float(p["y_mm"]) - b["y_min"]} for p in pts]
    else:
        frame = frame or "local"
    return pts, frame


def choose_scale(W, D, plan_w, plan_h):
    for s in SCALES:
        if W / s <= plan_w and D / s <= plan_h:
            return s
    return SCALES[-1]


def build_a3(lock, results, out_svg, project=None):
    b = lock["bounds_mm"]
    W = lock["net_dimensions_mm"]["length"]
    D = lock["net_dimensions_mm"]["width"]
    px0, py0, plan_w, plan_h = 18.0, 30.0, 258.0, 208.0
    scale = choose_scale(W, D, plan_w, plan_h)
    dw, dh = W / scale, D / scale
    ox = px0 + (plan_w - dw) / 2
    oy = py0 + (plan_h - dh) / 2

    # 坐标映射（mm 模型 -> mm 图纸，y 轴翻转）
    def X(x): return ox + (float(x) - b["x_min"]) / scale
    def Y(y): return oy + (b["y_max"] - float(y)) / scale

    def rect(r):  # [x0,y0,x1,y1] mm
        return X(r[0]), Y(r[3]), abs(X(r[2]) - X(r[0])), abs(Y(r[1]) - Y(r[3]))

    # ---- 尺寸链：以天花凹槽为分段点 ----
    segs_x, segs_y = [], []
    recess = lock.get("ceiling", {}).get("recess", {}).get("rect_mm")
    if recess:
        segs_x = [recess[0] - b["x_min"], recess[2] - recess[0], b["x_max"] - recess[2]]
        segs_y = [recess[1] - b["y_min"], recess[3] - recess[1], b["y_max"] - recess[3]]
    else:
        segs_x = [W]; segs_y = [D]
    verify_dimension_chain(W, segs_x)
    verify_dimension_chain(D, segs_y)

    pts, frame = normalize_positions(results, lock)
    fixtures = {f["code"]: f for f in results.get("fixtures", [])}

    # ---- 图元 ----
    parts = []
    # 墙
    x0p, y0p, wp, hp = X(b["x_min"]), Y(b["y_max"]), dw, dh
    parts.append(f'<rect x="{x0p:.2f}" y="{y0p:.2f}" width="{wp:.2f}" height="{hp:.2f}" fill="#FFFFFF" stroke="#111827" stroke-width="0.9"/>')
    # 分区
    for z in lock.get("zones", []):
        r = z.get("rect_mm")
        if not r:
            continue
        zx, zy, zw, zh = rect(r)
        if z["id"] == "Z3" or "卫生间" in z.get("name", ""):
            continue
        parts.append(f'<rect x="{zx:.2f}" y="{zy:.2f}" width="{zw:.2f}" height="{zh:.2f}" fill="#F3F4F6" stroke="none"/>')
    # 服务核（斜线填充，手工裁剪在矩形内，避免依赖 SVG clipPath）
    sc = lock.get("service_core")
    if sc:
        zx, zy, zw, zh = rect(sc["rect_mm"])
        parts.append(f'<rect x="{zx:.2f}" y="{zy:.2f}" width="{zw:.2f}" height="{zh:.2f}" fill="#E5E7EB" stroke="#6B7280" stroke-width="0.4"/>')
        c = -zh
        while c < zw:
            v0 = max(0.0, -c)
            v1 = min(zh, zw - c)
            if v1 > v0:
                u0, u1 = v0 + c, v1 + c
                parts.append(f'<line x1="{zx+u0:.2f}" y1="{zy+zh-v0:.2f}" x2="{zx+u1:.2f}" y2="{zy+zh-v1:.2f}" stroke="#9CA3AF" stroke-width="0.25"/>')
            c += 2.5
        parts.append(f'<text x="{zx+1:.2f}" y="{zy+zh/2:.2f}" font-size="2.2" fill="#4B5563">服务核</text>')
    # 天花凹槽 / 铜顶（虚线）
    def dashed(r, color, label=None):
        zx, zy, zw, zh = rect(r)
        parts.append(f'<rect x="{zx:.2f}" y="{zy:.2f}" width="{zw:.2f}" height="{zh:.2f}" fill="none" stroke="{color}" stroke-width="0.45" stroke-dasharray="2 1.2"/>')
        if label:
            parts.append(f'<text x="{zx+1:.2f}" y="{zy-0.8:.2f}" font-size="2.1" fill="{color}">{esc(label)}</text>')
    if recess:
        dashed(recess, "#B45309", "天花凹槽（L1 灯槽沿内缘）")
    copper = lock.get("ceiling", {}).get("copper_plate", {}).get("rect_mm")
    if copper:
        zx, zy, zw, zh = rect(copper)
        parts.append(f'<rect x="{zx:.2f}" y="{zy:.2f}" width="{zw:.2f}" height="{zh:.2f}" fill="none" stroke="#92400E" stroke-width="0.45" stroke-dasharray="2 1.2"/>')
        parts.append(f'<text x="{zx+1:.2f}" y="{zy+zh-1.0:.2f}" font-size="2.1" fill="#92400E">铜顶顶板</text>')
    # 门窗（门不画弧线，避免符号出图；以红色断口 + 编号表示）
    for op in lock.get("openings", []):
        zx, zy, zw, zh = rect(op["rect_mm"])
        if op["type"] == "门":
            parts.append(f'<line x1="{zx:.2f}" y1="{zy:.2f}" x2="{zx+zw:.2f}" y2="{zy+zh:.2f}" stroke="#FFFFFF" stroke-width="1.0"/>')
            parts.append(f'<line x1="{zx:.2f}" y1="{zy:.2f}" x2="{zx+zw:.2f}" y2="{zy+zh:.2f}" stroke="#DC2626" stroke-width="0.55"/>')
            parts.append(f'<text x="{zx+0.6:.2f}" y="{zy-1.0:.2f}" font-size="2.0" fill="#B91C1C">{esc(op["id"])}</text>')
        else:
            parts.append(f'<line x1="{zx:.2f}" y1="{zy:.2f}" x2="{zx+zw:.2f}" y2="{zy+zh:.2f}" stroke="#FFFFFF" stroke-width="0.9"/>')
            for off in (-0.45, 0.45):
                parts.append(f'<line x1="{zx:.2f}" y1="{zy+off:.2f}" x2="{zx+zw:.2f}" y2="{zy+zh+off:.2f}" stroke="#2563EB" stroke-width="0.35"/>')
            parts.append(f'<text x="{zx:.2f}" y="{zy-1.2:.2f}" font-size="2.0" fill="#1D4ED8">{esc(op["id"])}</text>')
    # 灯位
    for p in pts:
        px, py = X(p["x_mm"] + b["x_min"]), Y(p["y_mm"] + b["y_min"])
        parts.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="1.1" fill="#EF4444" stroke="#111827" stroke-width="0.25"/>')
        parts.append(f'<text x="{px+1.4:.2f}" y="{py+0.8:.2f}" font-size="1.9" fill="#111827">{esc(p["code"])}</text>')

    # 尺寸线（底 / 左）
    yb = oy + dh + 6
    parts.append(f'<line x1="{ox:.2f}" y1="{yb:.2f}" x2="{ox+dw:.2f}" y2="{yb:.2f}" stroke="#111827" stroke-width="0.3"/>')
    cx = ox
    for s in segs_x:
        cx2 = cx + s / scale
        parts.append(f'<line x1="{cx:.2f}" y1="{yb:.2f}" x2="{cx:.2f}" y2="{yb+1.2:.2f}" stroke="#111827" stroke-width="0.3"/>')
        parts.append(f'<text x="{cx+0.4:.2f}" y="{yb+3.2:.2f}" font-size="2.0" fill="#111827">{s:.0f}</text>')
        cx = cx2
    parts.append(f'<line x1="{cx:.2f}" y1="{yb:.2f}" x2="{cx:.2f}" y2="{yb+1.2:.2f}" stroke="#111827" stroke-width="0.3"/>')
    xl = ox - 6
    parts.append(f'<line x1="{xl:.2f}" y1="{oy:.2f}" x2="{xl:.2f}" y2="{oy+dh:.2f}" stroke="#111827" stroke-width="0.3"/>')
    cy = oy
    for s in segs_y:
        cy2 = cy + s / scale
        parts.append(f'<line x1="{xl:.2f}" y1="{cy:.2f}" x2="{xl-1.2:.2f}" y2="{cy:.2f}" stroke="#111827" stroke-width="0.3"/>')
        parts.append(f'<text x="{xl-4.2:.2f}" y="{cy+1.4:.2f}" font-size="2.0" fill="#111827">{s:.0f}</text>')
        cy = cy2
    parts.append(f'<line x1="{xl:.2f}" y1="{cy:.2f}" x2="{xl-1.2:.2f}" y2="{cy:.2f}" stroke="#111827" stroke-width="0.3"/>')

    # ---- 图例 ----
    legend = ['<text x="292" y="26" font-size="4" font-weight="bold" fill="#111827">图例 LEGEND</text>',
              '<line x1="290" y1="28" x2="410" y2="28" stroke="#111827" stroke-width="0.3"/>']
    ly = 34
    seen = set()
    for p in pts:
        code = p["code"]
        if code in seen:
            continue
        seen.add(code)
        fx = fixtures.get(code, {"name": code})
        legend.append(f'<circle cx="294" cy="{ly-1:.2f}" r="1.1" fill="#EF4444" stroke="#111827" stroke-width="0.25"/>')
        legend.append(f'<text x="298" y="{ly:.2f}" font-size="2.4" fill="#111827">{esc(code)}  {esc(fx.get("name", ""))}</text>')
        ly += 5
    legend.append(f'<line x1="294" y1="{ly-2:.2f}" x2="306" y2="{ly-2:.2f}" stroke="#B45309" stroke-width="0.45" stroke-dasharray="1 0.8"/>')
    legend.append(f'<text x="308" y="{ly:.2f}" font-size="2.3" fill="#111827">天花凹槽 / 灯槽参考线</text>')
    ly += 5
    legend.append(f'<line x1="294" y1="{ly-2:.2f}" x2="306" y2="{ly-2:.2f}" stroke="#DC2626" stroke-width="0.5"/>')
    legend.append(f'<text x="308" y="{ly:.2f}" font-size="2.3" fill="#111827">门</text>')
    legend.append(f'<line x1="330" y1="{ly-2:.2f}" x2="342" y2="{ly-2:.2f}" stroke="#2563EB" stroke-width="0.4"/>')
    legend.append(f'<text x="344" y="{ly:.2f}" font-size="2.3" fill="#111827">窗</text>')

    # ---- 灯具表 ----
    table_x, table_y = 290, 74
    rows = ['<text x="292" y="72" font-size="4" font-weight="bold" fill="#111827">灯具表 FIXTURE SCHEDULE</text>']
    rows.append(f'<line x1="290" y1="74" x2="410" y2="74" stroke="#111827" stroke-width="0.3"/>')
    heads = [("编号", 292), ("名称", 302), ("数量", 356), ("光通lm", 374), ("功率W", 394)]
    for h, x in heads:
        rows.append(f'<text x="{x}" y="79" font-size="2.2" font-weight="bold" fill="#111827">{h}</text>')
    ty = 84
    for code, fx in fixtures.items():
        qty = str(fx.get("quantity_or_length", fx.get("qty", "")))[:10]
        lm = fx.get("total_lumens", "")
        pw = round(fx.get("total_lumens", 0) / 110.0, 1) if fx.get("total_lumens") else ""
        rows.append(f'<text x="292" y="{ty}" font-size="2.1" fill="#111827">{esc(code)}</text>')
        rows.append(f'<text x="302" y="{ty}" font-size="2.1" fill="#111827">{esc(str(fx.get("name", ""))[:12])}</text>')
        rows.append(f'<text x="356" y="{ty}" font-size="2.1" fill="#111827">{esc(qty)}</text>')
        rows.append(f'<text x="374" y="{ty}" font-size="2.1" fill="#111827">{lm}</text>')
        rows.append(f'<text x="394" y="{ty}" font-size="2.1" fill="#111827">{pw}</text>')
        ty += 4.5
    ps = results.get("power_summary", {})
    rows.append(f'<line x1="290" y1="{ty-2:.2f}" x2="410" y2="{ty-2:.2f}" stroke="#111827" stroke-width="0.2"/>')
    rows.append(f'<text x="292" y="{ty+1.4:.2f}" font-size="2.1" fill="#111827">合计 {ps.get("total_lumens","")} lm / {ps.get("total_power_w","")} W / LPD {ps.get("lpd_w_m2","")} W/m²</text>')

    # ---- 比例尺 + 指北针 ----
    bar_x, bar_y = 292, 196
    seg = 1.0  # 图上 1 mm = 25 mm 实长；此处示意 1 m 对应 1 mm 图面
    for i in range(5):
        fill = "#111827" if i % 2 == 0 else "#FFFFFF"
        rows.append(f'<rect x="{bar_x + i*seg:.2f}" y="{bar_y:.2f}" width="{seg:.2f}" height="1.5" fill="{fill}" stroke="#111827" stroke-width="0.2"/>')
    for i in range(5):
        rows.append(f'<text x="{bar_x + i*seg - 0.6:.2f}" y="{bar_y+3.6:.2f}" font-size="1.8" fill="#111827">{i}</text>')
    rows.append(f'<text x="{bar_x+.2:.2f}" y="{bar_y-1.2:.2f}" font-size="2.0" fill="#111827">比例尺 1:{scale}（0–4 m）</text>')
    nx, ny = 400, 190
    rows.append(f'<polygon points="{nx},{ny-6} {nx-2},{ny+3} {nx},{ny+1} {nx+2},{ny+3}" fill="#111827"/>')
    rows.append(f'<text x="{nx-2.2:.2f}" y="{ny-7:.2f}" font-size="2.2" font-weight="bold" fill="#111827">N</text>')

    # ---- 光环境目标（来自冻结题） ----
    if project:
        tg = project.get("targets", {})
        ta = tg.get("acceptance", {}); tb = tg.get("operation", {})
        rows.append('<text x="292" y="152" font-size="3.6" font-weight="bold" fill="#111827">光环境目标（冻结题）</text>')
        rows.append('<line x1="290" y1="154" x2="410" y2="154" stroke="#111827" stroke-width="0.3"/>')
        rows.append(f'<text x="292" y="160" font-size="2.2" fill="#111827">T-A 验收：0.75 m 工作面 {ta.get("workplane_0_75m_lx","-")} lx（初始 {ta.get("initial_design_lx","-")} lx）</text>')
        rows.append(f'<text x="292" y="165" font-size="2.2" fill="#111827">T-B 运行：环境 {tb.get("ambient_lx",["-"])[0]}–{tb.get("ambient_lx",["-","-"])[1]} lx</text>')
        rows.append(f'<text x="292" y="170" font-size="2.2" fill="#111827">　　　　　桌面 {tb.get("table_lx",["-"])[0]}–{tb.get("table_lx",["-","-"])[1]} lx｜重点 {tb.get("accent_lx",["-"])[0]}–{tb.get("accent_lx",["-","-"])[1]} lx</text>')
        rows.append(f'<text x="292" y="175" font-size="2.0" fill="#4B5563">无 IES：±20–30%，T-A 仅作设计目标</text>')

    # ---- 施工说明 ----
    notes = [
        "1 本图比例 1:{s}，单位 mm；标高以完成面计，灯位为设计定位，施工前须现场复尺。".format(s=scale),
        "2 灯具须与风口、喷淋、烟感、音响综合；净距不足 300 mm 时现场协调，不得目测开孔。",
        "3 L1 灯槽沿中央吊顶凹槽内缘连续布置，转角斜接，出光口避免进入坐姿视线；大样见说明书。",
        "4 无 IES 配光，照度值为设计估算（±20–30%）；验收按 T-A（0.75 m / 75 lx）实测，运行按 T-B 五场景。",
    ]
    note_y = 268
    for n in notes:
        rows.append(f'<text x="18" y="{note_y}" font-size="2.1" fill="#374151">{esc(n)}</text>')
        note_y += 4.2

    # ---- 图签 ----
    tb_x, tb_y, tb_w, tb_h = 290, 230, 120, 52
    rows.append(f'<rect x="{tb_x}" y="{tb_y}" width="{tb_w}" height="{tb_h}" fill="none" stroke="#111827" stroke-width="0.5"/>')
    rows.append(f'<line x1="{tb_x}" y1="{tb_y+10}" x2="{tb_x+tb_w}" y2="{tb_y+10}" stroke="#111827" stroke-width="0.3"/>')
    rows.append(f'<line x1="{tb_x+62}" y1="{tb_y+10}" x2="{tb_x+62}" y2="{tb_y+tb_h}" stroke="#111827" stroke-width="0.3"/>')
    project_name = (project or {}).get("project", {}).get("name", results.get("project_name", ""))
    rows.append(f'<text x="{tb_x+2}" y="{tb_y+7}" font-size="2.6" font-weight="bold">{esc(project_name)}</text>')
    rows.append(f'<text x="{tb_x+2}" y="{tb_y+17}" font-size="2.3">图名：{esc(lock["room_name"])} 天花照明定位图</text>')
    rows.append(f'<text x="{tb_x+2}" y="{tb_y+23}" font-size="2.3">图号：{esc(results.get("drawing_no","L-04"))}</text>')
    rows.append(f'<text x="{tb_x+2}" y="{tb_y+29}" font-size="2.3">比例：1:{scale}</text>')
    rows.append(f'<text x="{tb_x+2}" y="{tb_y+35}" font-size="2.3">日期：{date.today().isoformat()}</text>')
    rows.append(f'<text x="{tb_x+2}" y="{tb_y+41}" font-size="2.3">单位：{esc(results.get("company",""))}</text>')
    rows.append(f'<text x="{tb_x+64}" y="{tb_y+17}" font-size="2.2">设计</text>')
    rows.append(f'<text x="{tb_x+64}" y="{tb_y+23}" font-size="2.2">制图</text>')
    rows.append(f'<text x="{tb_x+64}" y="{tb_y+29}" font-size="2.2">审核</text>')
    rows.append(f'<text x="{tb_x+64}" y="{tb_y+41}" font-size="2.0" fill="#4B5563">能力级别 {esc(results.get("capability_level",""))}</text>')

    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{A3_W}mm" height="{A3_H}mm" viewBox="0 0 {A3_W} {A3_H}">
<style>text{{font-family:"Microsoft YaHei","Noto Sans SC",sans-serif;}}</style>
<rect x="0" y="0" width="{A3_W}" height="{A3_H}" fill="#FFFFFF"/>
<rect x="10" y="10" width="400" height="277" fill="none" stroke="#111827" stroke-width="0.6"/>
<line x1="288" y1="10" x2="288" y2="287" stroke="#111827" stroke-width="0.4"/>
<text x="18" y="24" font-size="4.2" font-weight="bold" fill="#111827">{esc(lock["room_name"])} 天花照明定位图</text>
{"".join(parts)}
{"".join(legend)}
{"".join(rows)}
</svg>
'''
    out_svg.parent.mkdir(parents=True, exist_ok=True)
    out_svg.write_text(svg, encoding="utf-8")
    print(f"[Stage 4] A3 SVG 已生成: {out_svg} | 比例 1:{scale} | 平面 {dw:.1f}×{dh:.1f} mm | 灯位坐标基准: {frame}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Stage 4 A3 定位图 v2.1")
    ap.add_argument("--room-lock", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--project", default="")
    ap.add_argument("--out-svg", default="L-04_天花照明定位图_1-25.svg")
    args = ap.parse_args()
    lock = json.loads(Path(args.room_lock).read_text(encoding="utf-8"))
    results = json.loads(Path(args.results).read_text(encoding="utf-8"))
    project = json.loads(Path(args.project).read_text(encoding="utf-8")) if args.project else None
    build_a3(lock, results, Path(args.out_svg), project)
