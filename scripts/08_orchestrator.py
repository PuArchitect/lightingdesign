#!/usr/bin/env python3
"""
08_orchestrator.py (v2.1) — 多 Agent 协议的「驱动器」

它不替代 00_state_manager（状态机仍由它维护），而是给「人或模型」一个稳定的下一步入口：
  status        查看当前阶段、各阶段状态、缺什么产物、下一步做什么
  next          输出下一阶段该由哪个角色、读哪张卡、跑哪些命令
  start-stage   把阶段标记为 IN_PROGRESS
  verify-stage  阶段完成后的自动验证（产物 + 内容检查），通过才允许 checkpoint
  pack          生成 <=50 行交接单（调用 state_manager）
  stale         上游变更传播（调用 state_manager）

用法示例：
  python 08_orchestrator.py status --workdir work
  python 08_orchestrator.py next   --workdir work
  python 08_orchestrator.py start-stage  --workdir work --stage STAGE_1_GEOM
  python 08_orchestrator.py verify-stage --workdir work --stage STAGE_1_GEOM
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

import pymupdf as fitz

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("state_manager", HERE / "00_state_manager.py")
sm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sm)

ROLE_CARDS = {
    "STAGE_0_ENV": "agents/01_surveyor.md",
    "STAGE_1_GEOM": "agents/01_surveyor.md",
    "STAGE_2_STRATEGY": "agents/02_physicist.md",
    "STAGE_3_CALC": "agents/02_physicist.md",
    "STAGE_4_A3": "agents/03_designer.md",
    "STAGE_5_REPORT": "agents/03_designer.md",
    "STAGE_6_VQC": "agents/04_auditor.md",
    "STAGE_7_DELIVERY": "agents/04_auditor.md",
}
ROLE_NAMES = {
    "STAGE_0_ENV": "Agent A 测绘员", "STAGE_1_GEOM": "Agent A 测绘员",
    "STAGE_2_STRATEGY": "Agent B 物理工程师", "STAGE_3_CALC": "Agent B 物理工程师",
    "STAGE_4_A3": "Agent C 设计师", "STAGE_5_REPORT": "Agent C 设计师",
    "STAGE_6_VQC": "Agent D 审计员", "STAGE_7_DELIVERY": "Agent D 审计员",
}
NEXT_HINT = {
    "STAGE_0_ENV": ["python scripts/00_preflight_env.py --project-id <id> --out env_fingerprint.json"],
    "STAGE_1_GEOM": ["python scripts/01b_room_lock_from_project.py --project <冻结题> --canonical <实测几何> --out-json room_lock.json --out-png 00_房间边界确认图.png",
                     "★ 人工门禁：确认 00_房间边界确认图.png 后才能进入 Stage 2"],
    "STAGE_2_STRATEGY": ["按冻结题写 scheme_init.json（五层光策略 + T-A/T-B 双口径 + 5 场景）",
                         "★ 人工门禁：材质反射率假定与待确认清单需业主确认"],
    "STAGE_3_CALC": ["python scripts/02_rad_core.py（库）+ 项目计算脚本 -> results.json",
                     "python scripts/03_audit_closure.py --results results.json --out closure_audit.json"],
    "STAGE_4_A3": ["python scripts/04_render_svg_a3.py --room-lock room_lock.json --results results.json --project <冻结题> --out-svg L-04_..._1-25.svg",
                   "python scripts/tools/svg_to_a3_pdf.py --svg L-04_..._1-25.svg --out-pdf 02_L-04_..._A3.pdf"],
    "STAGE_5_REPORT": ["填充 templates/report_client.html -> report.html",
                       "python scripts/05_build_report_pdf.py --env env_fingerprint.json --html report.html --out-pdf 01_说明书.pdf --title <图名>"],
    "STAGE_6_VQC": ["python scripts/07_visual_qc_lint.py --pdf 01_说明书.pdf --a3 02_L-04_..._A3.pdf --png-dir qc_pngs",
                    "按需读图复核 6 类视觉缺陷，写 state/qc_issues.json"],
    "STAGE_7_DELIVERY": ["python scripts/06_preflight_delivery.py --delivery-dir <交付根> --project <冻结题> --manifest golden/manifests/<样本>.json --lint"],
}


def load(workdir: Path):
    state_file = workdir / "state" / "workflow_state.json"
    return sm.load_state(state_file)


def cmd_status(workdir: Path):
    st = load(workdir)
    print(f"project: {st['project_id']} | level: {st['capability_level']} | current: {st['current_stage']}")
    for s in sm.STAGE_ORDER:
        row = st["stages"][s]
        print(f"  {s:18s} {row['status']:9s} artifacts={len(row['artifacts'])}")
    nxt = next_stage(st)
    print(f"next: {nxt} ({ROLE_NAMES.get(nxt, '')})")
    if nxt != "DONE":
        missing = []
        for pattern in sm.REQUIRED_ARTIFACTS.get(nxt, []):
            hits = list(workdir.glob(pattern)) + list(workdir.glob(f"**/{pattern}"))
            if not hits:
                missing.append(pattern)
        print("missing:", "无" if not missing else ", ".join(missing))
        print(f"下一步: python 08_orchestrator.py start-stage --workdir {workdir} --stage {nxt}")
    return 0


def next_stage(st):
    for s in sm.STAGE_ORDER:
        if st["stages"][s]["status"] not in ("PASSED",):
            return s
    return "DONE"


def cmd_next(workdir: Path):
    st = load(workdir)
    s = next_stage(st)
    if s == "DONE":
        print("全部阶段已 PASSED。")
        return 0
    print(f"下一阶段: {s}")
    print(f"角色: {ROLE_NAMES.get(s, '?')}（角色卡: {ROLE_CARDS.get(s, '?')}）")
    print("必跑命令/动作:")
    for h in NEXT_HINT.get(s, []):
        print("  - " + h)
    print("完成后: python scripts/08_orchestrator.py verify-stage --workdir %s --stage %s" % (workdir, s))
    return 0


def cmd_start(workdir: Path, stage: str):
    state_file = workdir / "state" / "workflow_state.json"
    st = load(workdir)
    st["stages"][stage]["status"] = "IN_PROGRESS"
    sm.save_state(state_file, st)
    print(f"{stage} -> IN_PROGRESS")
    return 0


def _find(workdir: Path, pattern: str):
    hits = list(workdir.glob(pattern)) + list(workdir.glob(f"**/{pattern}"))
    return hits[0] if hits else None


def verify_stage(workdir: Path, stage: str, project: Path | None):
    errs, warns = [], []

    def need(pattern):
        p = _find(workdir, pattern)
        if p is None:
            errs.append(f"缺产物 {pattern}")
        return p

    if stage == "STAGE_0_ENV":
        p = need("env_fingerprint.json")
        if p:
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("capability_level") == "BLOCKED":
                errs.append("capability_level = BLOCKED")
            if not d.get("radiance_smoke", {}).get("passed") and str(d.get("capability_level")) == "L3":
                errs.append("声明 L3 但 Radiance 冒烟未通过")
    elif stage == "STAGE_1_GEOM":
        p = need("room_lock.json")
        need("00_房间边界确认图.png")
        if p:
            d = json.loads(p.read_text(encoding="utf-8"))
            for k in ("scope", "zones", "ceiling", "signoff", "net_dimensions_mm"):
                if k not in d:
                    errs.append(f"room_lock 缺 {k}")
            if project:
                proj = json.loads(project.read_text(encoding="utf-8"))
                pa = proj["scope"]["area_design_m2"]
                if pa > 0 and abs(d.get("net_area_m2", 0) - pa) / pa > 0.01:
                    errs.append(f"面积 {d.get('net_area_m2')} 与冻结题 {pa} 偏差 >1%")
            if d.get("discrepancies_to_confirm"):
                errs.append("存在几何冲突未确认: " + "; ".join(d["discrepancies_to_confirm"]))
            if not d.get("signoff", {}).get("confirmed_at"):
                warns.append("room_lock 尚无人工确认时间（人工门禁未签）")
    elif stage == "STAGE_2_STRATEGY":
        p = need("scheme_init.json")
        if p:
            d = json.loads(p.read_text(encoding="utf-8"))
            if not d.get("targets"):
                errs.append("scheme_init 缺 targets（T-A/T-B）")
            if not d.get("layers"):
                errs.append("scheme_init 缺 layers（五层光）")
    elif stage == "STAGE_3_CALC":
        rp = need("results.json")
        cp = need("closure_audit.json")
        if rp:
            d = json.loads(rp.read_text(encoding="utf-8"))
            for k in ("targets", "workplane_usable", "power_summary", "fixtures", "scenes"):
                if k not in d:
                    errs.append(f"results 缺 {k}")
            if project:
                proj = json.loads(project.read_text(encoding="utf-8"))
                pa = proj["scope"]["area_design_m2"]
                ra = d.get("power_summary", {}).get("room_area_m2", 0)
                if ra and abs(ra - pa) / pa > 0.01:
                    errs.append(f"results 面积 {ra} 与冻结题 {pa} 偏差 >1%")
        if cp:
            d = json.loads(cp.read_text(encoding="utf-8"))
            if not d.get("passed"):
                errs.append("closure_audit 未通过")
    elif stage == "STAGE_4_A3":
        p = need("*A3*.pdf")
        if p:
            doc = fitz.open(str(p)); r = doc[0].rect; text = doc[0].get_text(); doc.close()
            w, h = r.width * 25.4 / 72, r.height * 25.4 / 72
            if not ((abs(w - 420) <= .5 and abs(h - 297) <= .5) or (abs(w - 297) <= .5 and abs(h - 420) <= .5)):
                errs.append(f"A3 幅面 {w:.1f}×{h:.1f} mm 不符")
            if not any(k in text for k in ("图号", "图名")):
                errs.append("A3 文本层缺图号/图名")
    elif stage == "STAGE_5_REPORT":
        p = need("*.pdf")
        if p:
            doc = fitz.open(str(p)); n = doc.page_count
            text = "\n".join(pg.get_text() for pg in doc); doc.close()
            if not (6 <= n <= 16):
                warns.append(f"说明书 {n} 页，规范 8–12 页")
            for tok in ("T-A", "T-B"):
                if tok not in text:
                    errs.append(f"报告缺 {tok} 口径")
    elif stage == "STAGE_6_VQC":
        p = need("qc_lint_report.txt")
        need("qc_issues.json")
        if p:
            t = p.read_text(encoding="utf-8")
            if "FAIL=0" not in t and "FAIL = 0" not in t:
                errs.append("视觉 lint 未通过")
    elif stage == "STAGE_7_DELIVERY":
        p = need("preflight_delivery.txt")
        if p:
            t = p.read_text(encoding="utf-8")
            if "FAIL = 0" not in t and "FAIL=0" not in t:
                errs.append("终审 preflight 未通过")

    if errs:
        print(f"[verify {stage}] FAIL")
        for e in errs:
            print("  [FAIL]", e)
    else:
        print(f"[verify {stage}] PASS" + (f"（{len(warns)} WARN）" if warns else ""))
    for w in warns:
        print("  [WARN]", w)
    return 0 if not errs else 1


def main():
    ap = argparse.ArgumentParser(description="多 Agent 协议驱动器 (v2.1)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("status"); p.add_argument("--workdir", required=True); p.set_defaults(func=lambda a: cmd_status(Path(a.workdir)))
    p = sub.add_parser("next"); p.add_argument("--workdir", required=True); p.set_defaults(func=lambda a: cmd_next(Path(a.workdir)))
    p = sub.add_parser("start-stage"); p.add_argument("--workdir", required=True); p.add_argument("--stage", required=True)
    p.set_defaults(func=lambda a: cmd_start(Path(a.workdir), a.stage))
    p = sub.add_parser("verify-stage"); p.add_argument("--workdir", required=True); p.add_argument("--stage", required=True)
    p.add_argument("--project", default=""); p.set_defaults(func=lambda a: verify_stage(Path(a.workdir), a.stage, Path(a.project) if a.project else None))
    p = sub.add_parser("pack"); p.add_argument("--workdir", required=True); p.add_argument("--target-stage", required=True)
    p.set_defaults(func=lambda a: sm.cmd_pack_handoff(argparse.Namespace(workdir=a.workdir, target_stage=a.target_stage)))
    p = sub.add_parser("stale"); p.add_argument("--workdir", required=True)
    p.set_defaults(func=lambda a: sm.cmd_check_stale(argparse.Namespace(workdir=a.workdir)))
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
