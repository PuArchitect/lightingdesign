#!/usr/bin/env python3
"""
Stage 7: 最终交付物硬门禁自检 (lightingdesign v2.1)
v2.1 重写要点（相对 v2.0）：
  1) 接入冻结题（--project）：房间面积/尺寸与 project 一致性（±1%）、能力级别、T-A/T-B 双口径；
  2) Schema 校验（jsonschema 可用时；未安装则明确字段级降级，不假装有兜底）；room_lock 必须具备 scope/zones/ceiling/service_core/signoff 等 v2.1 字段；
  3) A3 检查从「物理幅面」升级为「幅面 + 文本层图号/图名/比例 + 灯位坐标在框内（从 SVG 源校验时）」；
  4) 交付清单：甲方包（说明书/A3/灯具表/五场景表/伪彩）+ 审计包（env/room_lock/results/closure/脚本）；
  5) 可选调用 golden/check_delivery.py（--manifest），跨平台回归；
  6) 结果落盘 preflight_delivery.txt（供状态机登记）。
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    import pymupdf as fitz
except Exception:
    fitz = None
try:
    from docx import Document
except Exception:
    Document = None

PT_TO_MM = 25.4 / 72.0


def read_text(p: Path) -> str:
    low = str(p).lower()
    if low.endswith(".pdf") and fitz:
        try:
            d = fitz.open(p); t = "\n".join(pg.get_text() for pg in d); d.close(); return t
        except Exception:
            return ""
    if low.endswith(".docx") and Document:
        try:
            d = Document(p)
            parts = [x.text for x in d.paragraphs]
            for tb in d.tables:
                for row in tb.rows:
                    for c in row.cells:
                        parts.append(c.text)
            return "\n".join(parts)
        except Exception:
            return ""
    for enc in ("utf-8", "utf-8-sig", "gbk", "utf-16"):
        try:
            return p.read_text(encoding=enc)
        except Exception:
            continue
    return ""


def pdf_pages(p: Path):
    if not fitz:
        return None
    d = fitz.open(p); n = d.page_count; d.close(); return n


def pdf_size_mm(p: Path):
    if not fitz:
        return None
    d = fitz.open(p); r = d[0].rect; d.close()
    return sorted([r.width * PT_TO_MM, r.height * PT_TO_MM])



def schema_check(obj, schema_name: str):
    """jsonschema 可用则真校验；不可用则明确降级为字段级校验，不再假装有 schema 兜底。"""
    sf = Path(__file__).resolve().parents[1] / "schemas" / schema_name
    if not sf.is_file():
        return True, f"schema 缺失（{schema_name}），已跳过"
    try:
        import jsonschema  # type: ignore
    except Exception:
        return True, "jsonschema 未安装：已做字段级校验（非 schema 校验）"
    try:
        jsonschema.validate(obj, json.loads(sf.read_text(encoding="utf-8")))
        return True, "jsonschema PASS"
    except Exception as e:
        return False, str(e).splitlines()[0][:140]

def main():
    ap = argparse.ArgumentParser(description="Stage 7 终审 v2.1")
    ap.add_argument("--delivery-dir", required=True)
    ap.add_argument("--project", default="")
    ap.add_argument("--manifest", default="", help="可选：golden manifest；给出则调用 golden/check_delivery.py")
    ap.add_argument("--golden-script", default="")
    ap.add_argument("--lint", action="store_true", help="可选：调用 07_visual_qc_lint.py 做确定性视觉/版式 lint")
    ap.add_argument("--lint-png-dir", default="", help="120 dpi 质检 PNG 目录（配合 --lint）")
    args = ap.parse_args()

    root = Path(args.delivery_dir)
    project = json.loads(Path(args.project).read_text(encoding="utf-8")) if args.project else None
    checks = []

    def rec(name, ok, detail):
        checks.append((name, ok, detail))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    # ---- 目录 ----
    client = root / "01_甲方汇报包"
    audit = root / "02_设计师复核与审计包"
    dual = client.is_dir() and audit.is_dir()
    rec("双轨目录", dual, "01_甲方汇报包 / 02_设计师复核与审计包" if dual else "缺双轨目录")
    rec("顶层 README", (root / "00_README.md").is_file(), "00_README.md")

    ssot = audit / "04_数据与审计" if dual else root / "04_数据与审计"
    for f in ("env_fingerprint.json", "room_lock.json", "results.json", "closure_audit.json"):
        rec(f"SSOT {f}", (ssot / f).is_file(), str(ssot / f))

    # ---- room_lock 语义 ----
    lock = None
    lp = ssot / "room_lock.json"
    if lp.is_file():
        try:
            lock = json.loads(lp.read_text(encoding="utf-8"))
            need = ["scope", "zones", "ceiling", "net_dimensions_mm", "net_area_m2", "signoff"]
            miss = [k for k in need if k not in lock]
            rec("room_lock 字段（v2.1）", not miss, "齐全" if not miss else f"缺 {miss}")
            ok_s, detail_s = schema_check(lock, "room_lock.schema.json")
            rec("room_lock Schema", ok_s, detail_s)
            if project:
                pa = project["scope"]["area_design_m2"]
                dev = abs(lock.get("net_area_m2", 0) - pa) / pa
                rec("房间面积 vs 冻结题", dev <= 0.01, f"lock {lock.get('net_area_m2')} m² / 冻结 {pa} m²（偏差 {dev:.1%}）")
                pw, pd = project["scope"]["size_m"]["W"], project["scope"]["size_m"]["D"]
                dm = lock.get("net_dimensions_mm", {})
                ew = abs(dm.get("length", 0) / 1000 - pw) / pw
                ed = abs(dm.get("width", 0) / 1000 - pd) / pd
                rec("房间尺寸 vs 冻结题", ew <= 0.01 and ed <= 0.01,
                    f"{dm.get('length',0)/1000:.2f}×{dm.get('width',0)/1000:.2f} m（冻结 {pw}×{pd}）")
        except Exception as e:
            rec("room_lock 解析", False, str(e))

    # ---- results 语义 ----
    results = None
    rp = ssot / "results.json"
    if rp.is_file():
        try:
            results = json.loads(rp.read_text(encoding="utf-8"))
            ps = results.get("power_summary", {})
            if project:
                pa = project["scope"]["area_design_m2"]
                ra = ps.get("room_area_m2", 0)
                dev = abs(ra - pa) / pa if ra else 1
                rec("results 面积 vs 冻结题", dev <= 0.01, f"{ra} m² / {pa} m²（偏差 {dev:.1%}）")
                req = project["capability"]["required_level"]
                lvl = str(results.get("capability_level", "")).upper()
                rec("能力级别", lvl.startswith(req), f"{lvl or '未声明'} / 要求 {req}")
            tgt = results.get("targets") or {}
            rec("results 含 targets", bool(tgt), "T-A/T-B" if tgt else "缺 targets（v2.1 schema）")
            prov = results.get("provenance") or {}
            rec("物理溯源", bool(prov), ", ".join(list(prov)[:5]) if prov else "缺 provenance")
            clo_p = ssot / "closure_audit.json"
            if clo_p.is_file():
                clo = json.loads(clo_p.read_text(encoding="utf-8"))
                rec("闭合校验", bool(clo.get("passed")), f"偏差 {clo.get('diff_pct','?')}%（阈值 {clo.get('threshold_pct','1')}%）")
            else:
                rec("闭合校验", False, "缺 closure_audit.json")
            ok_s, detail_s = schema_check(results, "results.schema.json")
            rec("results Schema", ok_s, detail_s)
        except Exception as e:
            rec("results 解析", False, str(e))

    # ---- 报告 ----
    if dual:
        reps = [p for p in client.glob("*.pdf") if "A3" not in p.name]
    else:
        reps = [p for p in root.rglob("*.pdf") if "A3" not in p.name]
    if reps:
        rep = reps[0]
        n = pdf_pages(rep)
        rec("说明书页数", n is not None and 5 <= n <= 20, f"{n} 页（页数不设硬门槛，5–20 合理）")
        size_mb = rep.stat().st_size / 1e6
        rec("报告体积（≤15 MB）", size_mb <= 15, f"{size_mb:.2f} MB")
        txt = read_text(rep)
        if project:
            ta = project["targets"]["acceptance"]; tb = project["targets"]["operation"]
            need = {
                "T-A 标签": r"(?<![A-Za-z])T-A(?![A-Za-z])", "T-B 标签": r"(?<![A-Za-z])T-B(?![A-Za-z])",
                "75 lx": r"75\s*lx", "40–60": r"40\s*[–\-~]\s*60", "90–150": r"90\s*[–\-~]\s*150",
                "300–500": r"300\s*[–\-~]\s*500",
            }
            miss = [k for k, pat in need.items() if not re.search(pat, txt, re.I)]
            rec("T-A + T-B 双口径", not miss, "齐全" if not miss else f"报告缺 {miss}")
        # 六类图（缺一即 FAIL）
        six = {
            "平面布局图": ("灯位" in txt or "定位图" in txt or "平面" in txt),
            "剖面示意图": ("剖面" in txt),
            "照度图": ("伪彩" in txt or "照度图" in txt or "false color" in txt.lower()),
            "大样图": ("大样" in txt or "节点" in txt),
            "灯光渲染图": ("渲染" in txt or "效果图" in txt),
            "灯具表": ("灯具表" in txt or "灯具清单" in txt),
        }
        for k, ok in six.items():
            rec(f"报告含六类图 · {k}", ok, "存在" if ok else "缺失")
        # 设计与交付完整性
        for token in ("设计依据", "待确认", "局限"):
            rec(f"报告章节 {token}", token in txt, "存在" if token in txt else "缺失")
        figs = sorted({int(x) for x in re.findall(r"图\s*(\d+)", txt)})
        rec("报告图表（≥3 张）", len(figs) >= 3, f"图号 {figs}")
        # 重复段落（忽略跨页 running header/footer，避免把页眉误判为重复段落）
        lines = []
        try:
            d = fitz.open(rep)
            plines = [[ln.strip() for ln in pg.get_text().splitlines() if ln.strip()] for pg in d]
            d.close()
            from collections import Counter
            freq = Counter()
            for ls in plines:
                freq.update(set(ls))
            n = len(plines)
            running = {ln for ln, c in freq.items()
                       if n >= 3 and c >= max(2, int(n * 0.5)) and len(ln) >= 8}
            lines = [ln for ls in plines for ln in ls if len(ln) >= 35 and ln not in running]
        except Exception:
            lines = [ln.strip() for ln in txt.splitlines() if len(ln.strip()) >= 35]
        dup = len(lines) - len(set(lines))
        rec("报告无重复段落", dup == 0, f"重复 {dup} 行（已忽略页眉/页脚）")
    else:
        rec("说明书 PDF", False, "未找到")

    # ---- README / 交接 / 质检预览 / 签核 ----
    n_pages = n if reps else 0
    readme_p = root / "00_README.md"
    if readme_p.is_file():
        rt = read_text(readme_p)
        ok_dual = ("01_甲方汇报包" in rt and "02_设计师复核" in rt)
        rec("README 双轨说明", ok_dual, "含双轨说明" if ok_dual else "缺双轨说明")
    else:
        rec("README 双轨说明", False, "缺 00_README.md")
    handovers = list(client.glob("*交接*.md")) + list(root.glob("*交接*.md"))
    rec("交接清单", bool(handovers), handovers[0].name if handovers else "缺交接清单")
    qc_dir = audit / "05_质检预览" if dual else root / "05_质检预览"
    if qc_dir.is_dir():
        n_qc = len(list(qc_dir.glob("*.png")))
        rec("质检预览页数", abs(n_qc - n_pages) <= 1, f"{n_qc} 张 vs 报告 {n_pages} 页")
    else:
        rec("质检预览页数", False, "缺 05_质检预览")
    state_f = (audit / "04_数据与审计" / "state" / "workflow_state.json") if dual else (root / "04_数据与审计" / "state" / "workflow_state.json")
    rec("state 签核", state_f.is_file(), "含 workflow_state.json" if state_f.is_file() else "缺 state/workflow_state.json")

    # ---- A3 ----
    a3s = list(client.glob("*A3*.pdf")) + list(root.rglob("*A3*.pdf"))
    a3s = list(dict.fromkeys(a3s))
    if a3s:
        a3 = a3s[0]
        sz = pdf_size_mm(a3)
        ok = sz and abs(sz[0] - 297.0) <= 0.5 and abs(sz[1] - 420.0) <= 0.5 or (sz and abs(sz[0] - 420.0) <= 0.5 and abs(sz[1] - 297.0) <= 0.5)
        rec("A3 物理幅面", bool(ok), f"{sz[0]:.1f}×{sz[1]:.1f} mm" if sz else "无法读取")
        t = read_text(a3)
        need_a3 = ["图名", "图号", "比例", "图例", "灯具表"]
        miss = [k for k in need_a3 if k not in t]
        rec("A3 文本层（图名/图号/比例/图例/灯具表）", not miss, "齐全" if not miss else f"缺 {miss}")
        m = re.search(r"1\s*[:：]\s*(\d{2,3})", t)
        rec("A3 比例标注", bool(m), f"1:{m.group(1)}" if m else "未找到 1:XX")
    else:
        rec("A3 PDF", False, "未找到 *A3*.pdf")

    # ---- 交付清单 ----
    if dual:
        need_client = {"说明书": list(client.glob("*说明书*.pdf")),
                       "平面布局图": list(client.glob("*A3*.pdf")),
                       "剖面示意图": list(client.glob("*剖面*.png")) + list(client.glob("*剖面*.svg")),
                       "照度图": list(client.glob("*伪彩*.png")) + list(client.glob("*照度*.png")),
                       "大样图": list(client.glob("*节点*.png")) + list(client.glob("*大样*.png")) + list(client.glob("*节点*.svg")),
                       "灯光渲染图": list(client.glob("*真彩*.png")) + list(client.glob("*渲染*.png")) + list(client.glob("*效果*.png")),
                       "灯具表": list(client.glob("*.xlsx")) + list(client.glob("*.csv"))}
        need_audit = {"脚本": list((audit / "03_原始矢量与网页").glob("*.py")) + list((audit / "04_数据与审计").glob("*.py")) + list(audit.rglob("*.py"))}
        for k, v in {**need_client, **need_audit}.items():
            rec(f"交付项 {k}", bool(v), f"{len(v)} 个文件")

    # ---- golden ----
    if args.manifest and project:
        gs = Path(args.golden_script) if args.golden_script else (Path(__file__).resolve().parents[1] / "golden" / "check_delivery.py")
        if gs.is_file():
            r = subprocess.run([sys.executable, str(gs), str(root), "--manifest", args.manifest,
                                "--project", str(args.project)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            rec("golden 校验", r.returncode == 0, (r.stdout or r.stderr).strip().splitlines()[-1] if (r.stdout or r.stderr) else "")
        else:
            rec("golden 校验", False, f"未找到 {gs}")

    # ---- 视觉/版式 lint（确定性部分，先于读图 QC）----
    if args.lint:
        lint_script = Path(__file__).resolve().parent / "07_visual_qc_lint.py"
        if lint_script.is_file() and reps:
            cmd = [sys.executable, str(lint_script), "--pdf", str(reps[0]),
                   "--out", str(root / "qc_lint_report.txt")]
            if a3s:
                cmd += ["--a3", str(a3s[0])]
            if args.lint_png_dir:
                cmd += ["--png-dir", args.lint_png_dir]
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            lines = [ln for ln in (r.stdout or "").strip().splitlines() if ln.strip()]
            summary_line = next((ln for ln in lines if ln.startswith("视觉/版式 lint")),
                                lines[-1] if lines else "无输出")
            rec("视觉/版式 lint", r.returncode == 0, summary_line)
        else:
            rec("视觉/版式 lint", False, "未找到 07_visual_qc_lint.py 或报告缺失")

    fails = [c for c in checks if not c[1]]
    summary = f"Stage 7 v2.1 终审：共 {len(checks)} 项，FAIL = {len(fails)}"
    print("\n" + summary)
    out = root / "preflight_delivery.txt"
    out.write_text(summary + "\n" + "\n".join(
        f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}" for name, ok, detail in checks), encoding="utf-8")
    print(f"结果已写入 {out}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
