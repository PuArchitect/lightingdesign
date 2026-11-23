# -*- coding: utf-8 -*-
"""S6 设计版报告 v2：HTML/CSS + PyMuPDF Story 逐页渲染。

NOTE: 本脚本是房间四示例，数据路径（R/D）按本机工作区写死；换项目请复制后改路径，
      主题通过 --theme themes/<project>.json 传入。
修复：表格固定列宽（table-layout:fixed）+ 控制图片宽度 + 收窄列数。
"""
import argparse
import base64
import io
import json
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageDraw, ImageFont

R = Path(r"D:\DeepSeekHarness\documents\lighting develop\research\result loop")
D = R / "_work" / "dsh" / "delivery"
AUD = D / "02_设计师复核与审计包" / "04_数据与审计"
OUT = R / "_work" / "dsh" / "_tools" / "report_story.pdf"
IMG = R / "_work" / "dsh" / "_tools" / "img"
IMG.mkdir(parents=True, exist_ok=True)
SKILL_ROOT = Path(__file__).resolve().parents[2]
_ap = argparse.ArgumentParser()
_ap.add_argument("--theme", default=str(SKILL_ROOT / "themes" / "neutral_light.json"))
_ap.add_argument("--out", default="")
_args, _ = _ap.parse_known_args()
THEME = json.loads(Path(_args.theme).read_text(encoding="utf-8"))
T = THEME["colors"]
if _args.out:
    OUT = Path(_args.out)

res = json.loads((AUD / "results.json").read_text(encoding="utf-8"))
lock = json.loads((AUD / "room_lock.json").read_text(encoding="utf-8"))
closure = json.loads((AUD / "closure_audit.json").read_text(encoding="utf-8"))
wu, wa, ps = res["workplane_usable"], res["workplane_active"], res["power_summary"]

_DEFAULT = {
    "bg": "#FCFAF6", "ink": "#241E18", "text_mid": "#3A2E24", "text_soft": "#4A3A2A",
    "muted": "#8A7A66", "accent": "#A8763E", "accent_dark": "#8B4A20",
    "table_head": "#F0E6D5", "table_head_ink": "#5A4632", "line": "#E8DDC9", "line_strong": "#D8C7AC",
    "note_bg": "#F6EFE2", "rh_line": "#DFD2BC",
    "cover_bg": "#221A14", "cover_title": "#F6EAD6", "cover_text": "#D9C6A9",
    "cover_kicker": "#B99A72", "cover_meta": "#C9A470", "cover_en": "#A8895F",
    "cover_border": "rgba(200,160,110,0.45)", "cover_border2": "rgba(200,160,110,0.35)",
}
_EXTRA = {"#B45309": "accent_dark", "#8B4A20": "accent_dark", "#92400E": "accent_dark",
          "#111827": "ink", "#0F172A": "ink", "#374151": "text_soft", "#4B5563": "text_soft",
          "#6B7280": "muted", "#9CA3AF": "muted", "#3A2E24": "text_mid", "#3A322A": "text_soft",
          "#4A3A2A": "text_soft", "#4A4038": "text_soft", "#5A4632": "table_head_ink",
          "#D8C7AC": "line_strong"}


def themed(s: str) -> str:
    for token, default in _DEFAULT.items():
        s = s.replace(default, T[token])
    for hx, token in _EXTRA.items():
        s = s.replace(hx, T[token])
    return s


CSS = """
@page { size: A4; margin: 0; }

body { margin: 0; font-family: "Microsoft YaHei"; color: #241E18; background: #FCFAF6; }
.sheet { width: 174mm; height: 297mm; padding: 20mm 0 16mm 18mm; }
.dark { background: #221A14; color: #F0E4D0; }
.rh { font-size: 7.4pt; letter-spacing: 1.1pt; color: #A08B6E; border-bottom: 0.5pt solid #DFD2BC; padding-bottom: 2.5mm; margin-bottom: 7mm; }
.secno { font-size: 8pt; letter-spacing: 2.5pt; color: #A8763E; margin-bottom: 2mm; }
h2 { font-size: 17pt; font-weight: 600; margin: 0 0 5mm; letter-spacing: 0.3pt; }
h3 { font-size: 10.5pt; font-weight: 600; margin: 5mm 0 2mm; color: #3A2E24; }
p { font-size: 9pt; line-height: 1.9; margin: 0 0 2.6mm; color: #3A322A; }
.lead { font-size: 9.5pt; line-height: 1.95; color: #3A2E24; }
.small { font-size: 8.1pt; line-height: 1.75; color: #4A4038; }
.cap { font-size: 7.3pt; color: #8A7A66; margin-top: 1.2mm; line-height: 1.5; }
table { width: 174mm; border-collapse: collapse; table-layout: fixed; font-size: 8.1pt; margin: 2mm 0 2.6mm; }
th { background: #F0E6D5; color: #5A4632; font-weight: 600; text-align: left; padding: 2.1mm 1.8mm; border-bottom: 0.5pt solid #D8C7AC; }
td { padding: 1.9mm 1.8mm; border-bottom: 0.3pt solid #E8DDC9; vertical-align: top; line-height: 1.5; }
td.c, th.c { text-align: center; }
td.num { font-family: "Consolas"; color: #6B3F1E; }
.note { background: #F6EFE2; border-left: 2.5pt solid #A8763E; padding: 2.8mm 3.6mm; font-size: 8pt; line-height: 1.75; color: #4A3A2A; margin: 3.2mm 0; }
.note b { color: #8B4A20; }
img { display: block; }
.center { text-align: center; }
.cover { width: 210mm; height: 297mm; background: #221A14; color: #F0E4D0; }
.cv { padding: 20mm; height: 297mm; border: 0.5pt solid rgba(200,160,110,0.45); margin: 9mm; }
.cv-top { font-size: 9pt; letter-spacing: 3.2pt; color: #C9A470; }
.cv-kick { margin-top: 52mm; font-size: 9.5pt; letter-spacing: 2.4pt; color: #B99A72; }
.cv-title { font-size: 60pt; font-weight: 300; letter-spacing: 3pt; color: #F6EAD6; margin: 6mm 0 4mm; }
.cv-en { font-size: 8.5pt; letter-spacing: 4pt; color: #A8895F; }
.cv-rule { width: 38mm; height: 1.2pt; background: #A8763E; margin: 12mm 0 10mm; }
.cv-quote { font-size: 13pt; line-height: 2.05; color: #D9C6A9; letter-spacing: 1pt; }
.cv-bot { margin-top: 52mm; border-top: 0.4pt solid rgba(200,160,110,0.35); padding-top: 4mm; font-size: 8.5pt; letter-spacing: 1.1pt; color: #C9A470; }
"""

CSS = themed(CSS)
CSS = CSS.replace('"Microsoft YaHei"', f'"{T.get("fonts", {}).get("body", "Microsoft YaHei")}"')


def to_jpg(src: Path, name: str, maxw=1600, q=86) -> Path:
    im = Image.open(src).convert("RGB")
    if im.width > maxw:
        im = im.resize((maxw, int(maxw * im.size[1] / im.size[0])), Image.LANCZOS)
    out = IMG / name
    im.save(out, "JPEG", quality=q, optimize=True)
    return out

def b64(p: Path) -> str:
    return base64.b64encode(p.read_bytes()).decode()


def font(size):
    for f in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"):
        try:
            return ImageFont.truetype(f, size)
        except Exception:
            continue
    return ImageFont.load_default()


def make_bar() -> Path:
    W, H = 1400, 700
    img = Image.new("RGB", (W, H), "#FCFAF6")
    d = ImageDraw.Draw(img)
    rows = [("中餐厅（一般照明）", 200, T["line_strong"]),
            ("咖啡厅 / 茶座", 120, T["line_strong"]),
            ("酒吧间（GB 50034 标准值）", 75, T["line_strong"]),
            ("本方案 · 0.75 m 工作面", 101.7, T["accent"]),
            ("本方案 · 迎宾场景", 40.8, T["cover_meta"]),
            ("本方案 · 影音场景", 6.6, T["accent_dark"])]
    x0, y, maxv = 50, 150, 210
    for label, v, color in rows:
        d.text((x0, y - 32), label, font=font(25), fill="#3A2E24")
        w = int((W - 430) * v / maxv)
        d.rectangle([x0, y, x0 + w, y + 30], fill=color)
        d.text((x0 + w + 12, y), f"{v:g} lx", font=font(25), fill="#6B3F1E")
        y += 88
    d.text((x0, 38), "水平照度比较（lx）", font=font(33), fill="#241E18")
    d.text((x0, 78), "0.75 m 参考面；暖色为本方案", font=font(21), fill="#8A7A66")
    out = IMG / "bar.png"
    img.save(out)
    return out


def make_plan() -> Path:
    a3 = D / "01_甲方汇报包" / "02_L-04_天花照明定位图_1-25_A3.pdf"
    doc = fitz.open(str(a3))
    pix = doc[0].get_pixmap(dpi=200)
    doc.close()
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    W, H = img.size
    crop = img.crop((int(W * 0.045), int(H * 0.11), int(W * 0.63), int(H * 0.87)))
    crop = crop.resize((1400, int(1400 * crop.size[1] / crop.size[0])), Image.LANCZOS)
    out = IMG / "plan_crop.png"
    crop.save(out)
    return out


def make_photo() -> Path:
    src = R / "local workbuddy+DeepSeek 4.1flash" / "00_输入资料" / "rendering" / "ROOM4-01_9.png"
    im = Image.open(src).convert("RGB")
    im = im.resize((1600, int(1600 * im.size[1] / im.size[0])), Image.LANCZOS)
    out = IMG / "room_photo.jpg"
    im.save(out, quality=88)
    return out


pseudo = D / "01_甲方汇报包" / "04_关键照度伪彩摘要图.png"
bar = make_bar()
plan = make_plan()
photo = make_photo()
render_main = to_jpg(IMG / "render_main.png", "render_main.jpg", 1200, 82)
render_cove = IMG / "render_cove.png"
detail = to_jpg(IMG / "detail_cove.png", "detail_cove.jpg", 1500, 85)
section = to_jpg(IMG / "section.png", "section.jpg", 1600, 86)
pseudo = to_jpg(pseudo, "pseudo.jpg", 1200, 82)


def tbl(headers, rows, widths, aligns=None):
    cols = "".join(f'<col style="width:{w}mm"/>' for w in widths)
    head = "".join(f'<th class="{(aligns[i] if aligns else "")}">{h}</th>' for i, h in enumerate(headers))
    body = ""
    for row in rows:
        cells = "".join(f'<td class="{(aligns[i] if aligns else "")}">{c}</td>' for i, c in enumerate(row))
        body += f"<tr>{cells}</tr>"
    return f'<table><colgroup>{cols}</colgroup><tr>{head}</tr>{body}</table>'


def page_cover():
    return """<div class="cover"><div class="cv">
<div class="cv-top">田野建筑　TIANYE ARCHITECTURE</div>
<div class="cv-kick">雪茄吧改造项目 · 室内照明</div>
<div class="cv-title">房间四</div>
<div class="cv-en">ROOM 4　·　LIGHTING DESIGN　·　L3</div>
<div class="cv-rule"></div>
<div class="cv-quote">以暗为底，以亮为点。<br/>光只照物，不照眼。</div>
<div class="cv-bot">图号　L-04　　版本　v2.1 · L3　　日期　2026.11.23</div>
</div></div>"""


def page_summary():
    rows = [
        ["设计面积", "20.35 m²（5.48 × 3.70 m）", "整间；统计剔除服务核约 1.1 m²"],
        ["净高 / 凹槽", "3.05 m / 3.72 × 3.04 m", "铜顶倒棱台，底 2.74 m"],
        ["工作面 0.75 m", f"{wu['avg_lx']} lx（Uo {wu['uo']:.2f}）", f"活动区 {wa['avg_lx']} lx（Uo {wa['uo']:.2f}）"],
        ["水平照度（清洁）", "100.9 lx", "T-A 目标 75 lx，初始设计 94 lx"],
        ["总光通 / 功率", f"{ps['total_lumens']} lm / {ps['total_power_w']} W", f"LPD {ps['lpd_w_m2']} W·m⁻²"],
        ["闭合校验", f"{closure['diff_pct']}%", f"{closure['sum_single_sources_lx']} lx vs {closure['main_avg_lx']} lx"],
    ]
    return f"""<div class="sheet">
<div class="rh">雪茄吧改造项目 · 房间四　｜　照明设计 · L3　｜　2026.11.23</div>
<div class="secno">01</div><h2>项目与结论摘要</h2>
<p class="lead">房间四是一间约 20.35 m² 的雪茄吧。四壁深色木饰面、顶部铜顶、东墙整面镜面；空间本身偏暗，设计的关键不是“照亮”，而是让铜、木、皮各有层次，把光留在需要的地方。</p>
<p class="small">设计依据：GB/T 50034-2024《建筑照明设计标准》、GB 55015-2021《建筑节能与可再生能源利用通用规范》、GB 51309-2018（如含应急）及业主设计任务书；几何以 3dm 完成面与冻结题为准。</p>
{tbl(["指标", "数值", "说明"], rows, [38, 64, 72])}
<div class="note"><b>一句话结论：</b>方案达到 T-A 验收目标（75 lx），同时把场景环境压到 40–60 lx；亮度集中在桌面、茶几与铜顶轮廓，不做均匀平铺。</div>
<h3>现状条件</h3>
{tbl(["部位", "现状"], [["四壁", "深色木饰面，反射率约 0.15；东墙整面镜面"], ["顶面", "铜顶倒棱台 + 跌级吊顶；中央凹槽 3.72 × 3.04 m"], ["北墙", "窗，白天需遮光策略"], ["东南角", "卫生间服务核约 1.1 m²，统计剔除，建模保留"]], [28, 146])}
<p class="small">能力级别 L3：几何 B-、配光 C（无 IES）、材质 C（铜顶/艺术漆待确认）。绝对照度不确定度 ±20–30%。</p>
</div>"""


def page_targets():
    rows = [
        ["<b>T-A 验收</b>", "0.75 m 工作面维持平均照度 <b>75 lx</b>（初始 94 lx，MF 0.80）", "GB/T 50034-2024 酒吧间；判定与报审"],
        ["<b>T-B 运行</b>", "环境 <b>40–60 lx</b>；桌面 <b>90–150 lx</b>；重点 <b>300–500 lx</b>", "五场景调光与氛围控制"],
        ["色温 / 显色", "2700 K 全线统一；Ra ≥ 90（重点 Ra ≥ 95）", "还原雪茄烟叶与威士忌的棕红"],
        ["眩光 / 频闪", "UGR &lt; 16；遮光角 ≥ 30°；SVM &lt; 0.4", "坐姿视线 1.1–1.3 m，光源不可见"],
    ]
    return f"""<div class="sheet">
<div class="rh">雪茄吧改造项目 · 房间四　｜　照明设计 · L3　｜　2026.11.23</div>
<div class="secno">02</div><h2>光环境目标：两套口径</h2>
<p class="lead">雪茄吧不是“照亮房间”，是照亮物件与人。T-A 用于判定与报审，T-B 用于场景与调光；两套并列，不混用。</p>
{tbl(["口径", "目标", "依据 / 用途"], rows, [30, 84, 60])}
<img src="data:image/png;base64,{b64(bar)}" style="width:160mm"/>
<div class="cap">图 1　水平照度比较：本方案（暖色）落在酒吧间标准与一般餐厅之间。</div>
<h3>与规范的关系</h3>
<p class="small">GB/T 50034-2024 对酒吧间的一般照明参考值为 75 lx。本方案 0.75 m 工作面 101.7 lx，清洁模式 100.9 lx，满足标准；场景环境压到 40–60 lx 是氛围型空间的主动取舍，需在验收时以清洁模式作为照度检验工况。</p>
<div class="note"><b>不做的事：</b>不做均匀布灯；不在镜面与电视屏幕前设直射光；不用 3000 K 以上冷白；不把 LOGO 背光当主光源。</div>
</div>"""


def page_strategy():
    rows = [
        ["L1 氛围", "铜顶暗藏灯槽", "勾亮铜顶裙边，形成顶部暖色轮廓", "13.48 m"],
        ["L2 环境", "跌级洗墙灯槽", "洗亮木饰面墙，提供使用面照度", "14.1 m"],
        ["L3 重点", "三头射灯", "茶几与座位之间的光的落点", "3 只"],
        ["L4 竖向", "壁灯", "深色墙面的亮度支撑", "2 只"],
        ["L5/L6 细节", "台灯 + LOGO 背光", "低位暖光与西墙视觉锚点", "1 只 / 0.27 m²"],
        ["L7 工作面", "下照筒灯", "工作面主力照度", "11 只"],
    ]
    return f"""<div class="sheet">
<div class="rh">雪茄吧改造项目 · 房间四　｜　照明设计 · L3　｜　2026.11.23</div>
<div class="secno">03</div><h2>分层照明策略</h2>
<p>五层光，各司其职。前期探针显示：洗墙对座位的单位光通效率约为铜顶灯槽的 4 倍，所以环境光以洗墙为主，灯槽只做轮廓；三头射灯只做茶几重点。</p>
{tbl(["层", "光源", "作用", "数量 / 长度"], rows, [20, 48, 78, 28])}
<div class="center"><img src="data:image/png;base64,{b64(plan)}" style="width:158mm"/></div>
<div class="cap">图 2　灯位示意（裁自 A3 图 L-04，定位尺寸以 A3 为准）。</div>
</div>"""


def page_calc():
    rows = [
        ["工作面 0.75 m（可用区）", f"{wu['avg_lx']}", f"{wu['min_lx']} / {wu['max_lx']}", f"{wu['uo']:.2f}"],
        ["工作面 0.75 m（活动区）", f"{wa['avg_lx']}", "—", f"{wa['uo']:.2f}"],
        ["座位眼高 1.20 m", "146.6", "136.6 / 152.4", "0.93"],
        ["茶几面 0.30 m", "132.2", "123.7 / 140.7", "0.94"],
    ]
    return f"""<div class="sheet">
<div class="rh">雪茄吧改造项目 · 房间四　｜　照明设计 · L3　｜　2026.11.23</div>
<div class="secno">06</div><h2>计算结果（L3 逐点）</h2>
{tbl(["测面", "平均 lx", "最小 / 最大", "Uo"], rows, [78, 28, 40, 28], ["", "c", "c", "c"])}
<img src="data:image/png;base64,{b64(pseudo)}" style="width:160mm"/>
<div class="cap">图 6　0.75 m 工作面伪彩图（单位 lx）；网格 0.5 m，C 级配光；可用区 37 点、活动区 23 点。</div>
<div class="note"><b>闭合校验 {closure['diff_pct']}%：</b>单光源贡献之和 {closure['sum_single_sources_lx']} lx 与主计算 {closure['main_avg_lx']} lx 一致（阈值 1%）。LPD {ps['lpd_w_m2']} W·m⁻²，低于 7 W·m⁻² 的通用要求。</div>
</div>"""


def page_fixtures():
    frows = [[f["code"], f["name"], f.get("quantity_or_length", ""), f.get("total_lumens", "")] for f in res["fixtures"]]
    frows.append(["<b>合计</b>", "", "", f"<b>{ps['total_lumens']}</b>"])
    srows = []
    for s in res["scenes"]:
        ratio = " / ".join(f"{s['dimming_ratios'].get(k, 0)}%" for k in ("L1", "L2", "L3", "L4", "L5", "L6", "L7"))
        srows.append([s["name"], f"L1–L7：{ratio}", f"{s['estimated_avg_lx']}"])
    return f"""<div class="sheet">
<div class="rh">雪茄吧改造项目 · 房间四　｜　照明设计 · L3　｜　2026.11.23</div>
<div class="secno">08</div><h2>灯具表与五场景</h2>
{tbl(["编号", "灯具", "数量 / 长度", "光通 lm"], frows, [16, 78, 46, 34], ["", "", "", "c"])}
<p class="small">系统功率 {ps['total_power_w']} W（110 lm/W 系统光效），LPD {ps['lpd_w_m2']} W·m⁻²。</p>
<h3>五场景调光（回路调光比例）</h3>
{tbl(["场景", "L1 / L2 / L3 / L4 / L5 / L6 / L7", "估算 lx"], srows, [28, 116, 30], ["", "", "c"])}
<p class="small">场景照度为“单源贡献 × 调光比例”线性估算，用于调光策略与氛围比较，不作为验收值。</p>
<h3>控制与回路</h3>
{tbl(["回路", "灯具", "控制"], [["CH1", "L1 铜顶灯槽（北/南）", "DALI 1–100%"], ["CH2", "L1 铜顶灯槽（东/西）", "DALI 1–100%"], ["CH3", "L2 跌级洗墙", "DALI 1–100%"], ["CH4", "L3 三头射灯", "DALI 1–100%"], ["CH5", "L4 壁灯 + L5 台灯 + L6 LOGO", "DALI / 插座"], ["CH6", "L7 下照筒灯", "DALI 1–100%，可分区"]], [16, 110, 48])}
</div>"""


def page_close():
    rows = [
        ["1", "无 IES 配光文件，C 级配光，绝对照度 ±20–30%；取得 IES 后重算。"],
        ["2", "铜顶 / 艺术铜漆反射率未确认，直接影响顶部与墙面亮度。"],
        ["3", "灯槽腔体做法与检修口（3dm 反推净宽约 15 mm），需施工方确认可安装性。"],
        ["4", "L7 筒灯开孔位置：模型无对应灯孔，需设计师确认。"],
        ["5", "北墙窗白天遮光策略、应急照明（GB 51309-2018）责任界面未定。"],
        ["6", "T-A/T-B 已确认；若业主要求更暗，按业主决策记录，不写成达标。"],
    ]
    return f"""<div class="sheet">
<div class="rh">雪茄吧改造项目 · 房间四　｜　照明设计 · L3　｜　2026.11.23</div>
<div class="secno">09</div><h2>施工、维护与待确认</h2>
<h3>施工要点</h3>
<p class="small">灯位放线须与天花、风口、喷淋、烟感、音响综合，净距不足 300 mm 时现场协调。灯槽封板前必须通电试亮：蹲下沿吊边看一圈，无断点、无色差、只见光带不见灯珠。射灯选可擦洗面罩；烟油结膜后按季度清洁；灯带建议 3 年后整体更换。</p>
<h3>待确认（6 项）</h3>
{tbl(["#", "事项"], rows, [10, 164], ["c", ""])}
<h3>验收：三个动作</h3>
<p class="small">① 清洁模式实测 0.75 m 工作面维持照度 ≥75 lx；② 按五场景走一遍，确认亮度曲线与氛围；③ 检查铜顶裙边无断点、无灯珠、无色差。</p>
<h3>灯槽最常见的三种做错法</h3>
<p class="small">① 灯槽太浅，坐下就能看到灯珠；② 灯带贴死在板上，出光一条亮一条暗；③ 转角没有斜接，阴角出现黑段。封板前按这三条逐项拍照留档。</p>
<div class="note">本报告不含施工图深度内容（电气回路、调光器选型、UGR 计算）；结论以模型几何与推定材质为前提，材质或做法变更后须重算。</div>
<h3>局限</h3>
<p class="small">① 无 IES 配光，配光按 C 级，绝对照度 ±20–30%；② 铜顶/艺术漆反射率未确认；③ 无 UGR 与眩光实测；④ 场景照度为线性估算，非 Radiance 场景重跑；⑤ 甲供效果图仅用于氛围参考，不是本方案计算输出。</p>
<p class="small" style="margin-top:8mm">田野建筑　TIANYE ARCHITECTURE　｜　雪茄吧改造项目 · 房间四照明设计　｜　v2.1 · L3　｜　2026.11.23</p>
<p class="small" style="margin-top:2mm">主控复验：24 项终审 0 FAIL ｜ golden 7/7 ｜ 视觉 lint 0 FAIL / 0 WARN</p>
</div>"""


def page_space():
    return f"""<div class="sheet">
<div class="rh">雪茄吧改造项目 · 房间四　｜　照明设计 · L3　｜　2026.11.23</div>
<div class="secno">05</div><h2>空间与光</h2>
<p class="lead">从入口看，铜顶是唯一的亮面，木饰面退到暗部；坐下后，茶几与桌面被三头射灯和筒灯托住，座位眼高不直对光源。</p>
<img src="data:image/jpeg;base64,{b64(photo)}" style="width:174mm"/>
<div class="cap">图 4　空间效果（甲方提供效果图，非本次计算输出；用于确认氛围与材质基调）。</div>
<img src="data:image/png;base64,{b64(render_main)}" style="width:132mm;margin-top:4mm"/>
<div class="cap">图 5　计算真彩渲染（Radiance，材料按 C 级推定，颜色偏灰；与 results 同一场景）。</div>
</div>"""


def page_detail():
    rows = [["灯槽净宽", "15 mm（3dm 反推，需厂家确认可安装）"],
            ["铜顶退台", "240 mm（凹槽边至铜顶板）"],
            ["凹槽高 / 铜顶标高", "290 mm / 3.04 m（吊顶完成面 2.50 m）"],
            ["出光口遮光角", "≥ 30°，坐姿视线 1.1–1.3 m 不见光源"]]
    return f"""<div class="sheet">
<div class="rh">雪茄吧改造项目 · 房间四　｜　照明设计 · L3　｜　2026.11.23</div>
<div class="secno">07</div><h2>灯槽节点与安装条件</h2>
<img src="data:image/png;base64,{b64(detail)}" style="width:174mm"/>
<div class="cap">图 7　A—A 灯槽节点大样（示意 1:5）：铜顶退台 240、凹槽高 290、灯槽净宽 15 mm。</div>
{tbl(["项", "控制值"], rows, [34, 140])}
<h3>安装顺序</h3>
{tbl(["步骤", "做法", "验收动作"], [["1", "灯槽基层与铜顶收边完成，预留 15 mm 槽", "核对槽宽、槽深与灯带宽度"], ["2", "灯带贴槽外侧，接通临时电", "通电试亮，蹲下看一圈无断点/灯珠"], ["3", "封板、收口、成品保护", "拍照留档，记录色差与转角"]], [14, 96, 64])}
<p class="small">① 封板前通电试亮：蹲下沿吊边看一圈，无断点、无色差、只见光带不见灯珠；② 灯带贴槽外侧，出光擦铜顶，不直射坐姿视线；③ 转角斜接，避免阴角黑段。</p>
</div>"""


def page_section():
    return f"""<div class="sheet">
<div class="rh">雪茄吧改造项目 · 房间四　｜　照明设计 · L3　｜　2026.11.23</div>
<div class="secno">04</div><h2>剖面示意</h2>
<p class="lead">剖面回答“光洗哪里、什么高度、什么关系”：铜顶灯槽只洗亮中央铜顶，不做环境光；环境光由跌级洗墙与下照筒灯承担，壁灯补竖向亮度。</p>
<img src="data:image/jpeg;base64,{b64(section)}" style="width:174mm"/>
<div class="cap">图 3　房间四横剖面示意（示意，不按比例用于施工；定位尺寸以 A3 图 L-04 为准）。</div>
<div class="note"><b>读图：</b>中央天花 +3.040、吊边 +2.740（宽 240）、壁灯 1.60、沙发/茶几 0.45；灯槽出光向上，避免坐姿视线看到光源。</div>
{tbl(["部位", "标高 / 尺寸", "光的作用"], [["中央天花", "+3.040", "灯槽向上洗亮铜顶，形成顶部轮廓"], ["吊边", "+2.740（宽 240）", "藏灯槽，坐姿看不到光源"], ["壁灯", "1.60", "补深色木饰面的竖向亮度"], ["沙发 / 茶几", "0.45", "使用面，由射灯与筒灯托住"]], [34, 46, 94])}
</div>"""


def render_page(html: str, out_pdf: Path) -> int:
    html = themed(html)
    story = fitz.Story(html=f"<html><head><style>{CSS}</style></head><body>{html}</body></html>")
    writer = fitz.DocumentWriter(str(out_pdf))
    mb = fitz.paper_rect("a4")
    dev = writer.begin_page(mb)
    story.place(mb)
    story.draw(dev)
    writer.end_page()
    writer.close()
    d = fitz.open(str(out_pdf))
    n = d.page_count
    d.close()
    return n


pages = [page_cover, page_summary, page_targets, page_strategy, page_section, page_space, page_calc, page_detail, page_fixtures, page_close]
tmp = IMG / "pages"
tmp.mkdir(exist_ok=True)
master = fitz.open()
for i, fn in enumerate(pages, start=1):
    p = tmp / f"p{i}.pdf"
    n = render_page(fn(), p)
    if n != 1:
        raise RuntimeError(f"page {i} overflowed to {n} pages")
    d = fitz.open(str(p))
    master.insert_pdf(d)
    d.close()

for i, pg in enumerate(master, start=1):
    r = pg.rect
    pg.insert_text((r.width - 62, r.height - 30), f"{i:02d} / {len(pages):02d}",
                   fontsize=7.5, color=(0.63, 0.58, 0.50),
                   fontname="msyh", fontfile=r"C:\Windows\Fonts\msyh.ttc")
master.set_metadata({"title": "雪茄吧房间四照明设计方案", "author": ""})
try:
    master.subset_fonts()
except Exception as e:
    print("subset_fonts skipped:", e)
master.save(str(OUT), deflate=True, deflate_images=True, deflate_fonts=True, garbage=4, clean=True)
print("saved", OUT, "pages", master.page_count)
