#!/usr/bin/env python3
"""
Multi-Agent 状态机、断点续传与上下文压缩管理器 (lightingdesign v2.0)
管理 state/ 下的三个核心协作文件:
  1. state/workflow_state.json  (阶段状态机 + 产物 MD5 + 下游失效传播)
  2. state/decision_log.jsonl   (只追加的防失忆决策账本)
  3. state/handoff_brief.md     (硬上限 <=50 行的上下文压缩交接单)

用法示例:
  python 00_state_manager.py init --workdir ./work_room4 --project-id cigar_room4
  python 00_state_manager.py checkpoint --workdir ./work_room4 --stage STAGE_1_GEOM --status PASSED --artifact room_lock.json
  python 00_state_manager.py add-decision --workdir ./work_room4 --stage STAGE_2_STRATEGY --author user --rule "取消西墙洗墙灯槽，LOGO背景墙刻意压暗"
  python 00_state_manager.py check-stale --workdir ./work_room4
  python 00_state_manager.py pack-handoff --workdir ./work_room4 --target-stage STAGE_4_A3
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

STAGE_ORDER = [
    "STAGE_0_ENV",
    "STAGE_1_GEOM",
    "STAGE_2_STRATEGY",
    "STAGE_3_CALC",
    "STAGE_4_A3",
    "STAGE_5_REPORT",
    "STAGE_6_VQC",
    "STAGE_7_DELIVERY",
]

STAGE_OWNER = {
    "STAGE_0_ENV": "01_surveyor",
    "STAGE_1_GEOM": "01_surveyor",
    "STAGE_2_STRATEGY": "02_physicist",
    "STAGE_3_CALC": "02_physicist",
    "STAGE_4_A3": "03_designer",
    "STAGE_5_REPORT": "03_designer",
    "STAGE_6_VQC": "04_auditor",
    "STAGE_7_DELIVERY": "04_auditor",
}

MAX_HANDOFF_LINES = 50

# v2.1：每个阶段 PASSED 时必须登记的产物（相对 workdir 的匹配模式，支持 glob）
REQUIRED_ARTIFACTS = {
    "STAGE_0_ENV": ["env_fingerprint.json"],
    "STAGE_1_GEOM": ["room_lock.json", "00_房间边界确认图.png"],
    "STAGE_2_STRATEGY": ["scheme_init.json"],
    "STAGE_3_CALC": ["results.json", "closure_audit.json"],
    "STAGE_4_A3": ["*A3*.pdf"],
    "STAGE_5_REPORT": ["*说明书*.pdf"],
    "STAGE_6_VQC": ["qc_issues.json"],
    "STAGE_7_DELIVERY": ["preflight_delivery.txt"],
}



def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def state_paths(workdir: Path) -> tuple[Path, Path, Path]:
    sdir = workdir / "state"
    sdir.mkdir(parents=True, exist_ok=True)
    return (
        sdir / "workflow_state.json",
        sdir / "decision_log.jsonl",
        sdir / "handoff_brief.md",
    )


def load_state(state_file: Path) -> dict:
    if not state_file.is_file():
        raise FileNotFoundError(f"未找到状态文件: {state_file}，请先执行 init。")
    return json.loads(state_file.read_text(encoding="utf-8"))


def save_state(state_file: Path, data: dict) -> None:
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    state_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def cmd_init(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir).resolve()
    state_file, log_file, brief_file = state_paths(workdir)

    stages = {
        st: {
            "owner": STAGE_OWNER[st],
            "status": "PENDING",
            "artifacts": {},
            "retry_count": 0,
            "updated_at": None,
        }
        for st in STAGE_ORDER
    }
    stages["STAGE_6_VQC"]["max_rounds"] = 3

    data = {
        "schema_version": "2.0",
        "project_id": args.project_id,
        "workdir": str(workdir),
        "capability_level": "UNKNOWN",
        "current_stage": STAGE_ORDER[0],
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "stages": stages,
    }
    save_state(state_file, data)
    if not log_file.exists():
        log_file.write_text("", encoding="utf-8")
    if not brief_file.exists():
        brief_file.write_text(
            f"# Handoff Brief · {args.project_id}\n\n- 状态：已初始化，等待 Stage 0 执行。\n",
            encoding="utf-8",
        )
    print(f"[StateManager] 已初始化工作流状态机: {state_file}")
    return 0


def cmd_checkpoint(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir).resolve()
    state_file, log_file, _ = state_paths(workdir)
    data = load_state(state_file)

    stage = args.stage
    if stage not in STAGE_ORDER:
        raise ValueError(f"未知阶段: {stage}，可选: {STAGE_ORDER}")

    # v2.1 门禁：前序阶段必须 PASSED（除非 --force，并写入决策账本）
    idx = STAGE_ORDER.index(stage)
    if idx > 0 and not args.force:
        pending = [s for s in STAGE_ORDER[:idx] if data["stages"][s]["status"] != "PASSED"]
        if pending:
            raise RuntimeError(f"门禁拦截：{stage} 之前仍有未通过阶段 {pending}。"
                               f"如确需跳过，使用 --force 并把原因写入 --force-reason。")
    if args.force:
        if not args.force_reason:
            raise RuntimeError("使用 --force 必须提供 --force-reason（会写入 decision_log.jsonl）。")
        entry = {"timestamp": datetime.now().isoformat(timespec="seconds"), "stage": stage,
                 "author": "user", "impact_stages": ["ALL"], "rule": f"[FORCE] {args.force_reason}"}
        with log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    st_obj = data["stages"][stage]
    st_obj["status"] = args.status
    st_obj["updated_at"] = datetime.now().isoformat(timespec="seconds")
    if args.status == "RETRY":
        st_obj["retry_count"] = st_obj.get("retry_count", 0) + 1

    if args.capability_level:
        fp = workdir / "env_fingerprint.json"
        if fp.is_file():
            actual = json.loads(fp.read_text(encoding="utf-8")).get("capability_level")
            if actual and actual != args.capability_level:
                raise RuntimeError(f"门禁拦截：checkpoint 声明 {args.capability_level}，但 env_fingerprint 实测 {actual}；不允许把 L2 写成 L3。")
        data["capability_level"] = args.capability_level

    for art in args.artifact or []:
        art_path = (workdir / art) if not Path(art).is_absolute() else Path(art)
        if not art_path.is_file():
            raise FileNotFoundError(f"门禁拦截：声明的产物文件不存在 -> {art_path}")
        rel_key = str(art_path.relative_to(workdir)) if art_path.is_relative_to(workdir) else str(art_path)
        st_obj["artifacts"][rel_key] = md5_file(art_path)

    # v2.1：PASSED 时校验该阶段必需产物存在（支持 workdir 与 state 同级目录的 glob）
    if args.status == "PASSED":
        missing = []
        for pattern in REQUIRED_ARTIFACTS.get(stage, []):
            hits = list(workdir.glob(pattern)) + list(workdir.glob(f"**/{pattern}"))
            if not hits:
                missing.append(pattern)
        if missing:
            raise RuntimeError(f"门禁拦截：{stage} PASSED 缺少必需产物 {missing}。"
                               f"请先生成并 checkpoint --artifact，或使用 --force。")

    # 若当前阶段通过，自动推进 current_stage 指针
    idx = STAGE_ORDER.index(stage)
    if args.status == "PASSED":
        data["current_stage"] = STAGE_ORDER[idx + 1] if idx + 1 < len(STAGE_ORDER) else "DONE"
    else:
        data["current_stage"] = stage

    save_state(state_file, data)
    # v2.3：每次 checkpoint 重写交接单，避免 handoff 停留在「等待 Stage 0」
    brief = workdir / "state" / "handoff_brief.md"
    try:
        arts = data["stages"][stage].get("artifacts", {})
        lines = [
            f"# Handoff Brief · {data.get('project_id','')}",
            f"- 更新时间：{datetime.now().isoformat(timespec='seconds')}",
            f"- 当前阶段：{stage} -> {args.status}",
            f"- 下一阶段：{data['current_stage']}",
            f"- 本阶段产物：{len(arts)} 个（{', '.join(list(arts)[:4])}）",
            f"- 能力级别：{data.get('capability_level','UNKNOWN')}",
            "- 未决事项与口径决策见 state/decision_log.jsonl；接手者先读本单，不读旧日志。",
        ]
        brief.write_text("\n".join(lines[:50]), encoding="utf-8")
    except Exception:
        pass
    if data["current_stage"] == "DONE":
        print(f"[StateManager] {stage} -> {args.status} | 全部阶段完成（DONE）")
    else:
        print(f"[StateManager] {stage} -> {args.status} | 下一阶段: {data['current_stage']}")
    return 0


def cmd_check_stale(args: argparse.Namespace) -> int:
    """校验各已完成阶段的产物 MD5，若上游文件被修改，自动将下游全部标为 STALE。"""
    workdir = Path(args.workdir).resolve()
    state_file, _, _ = state_paths(workdir)
    data = load_state(state_file)

    first_stale_idx = None
    for idx, st in enumerate(STAGE_ORDER):
        st_obj = data["stages"][st]
        if st_obj["status"] != "PASSED":
            continue
        for rel_path, saved_md5 in st_obj.get("artifacts", {}).items():
            full_path = workdir / rel_path
            if not full_path.is_file() or md5_file(full_path) != saved_md5:
                print(f"  [STALE] 上游产物已变更或缺失: {st} -> {rel_path}")
                first_stale_idx = idx
                break
        if first_stale_idx is not None:
            break

    if first_stale_idx is not None:
        for st in STAGE_ORDER[first_stale_idx:]:
            if data["stages"][st]["status"] == "PASSED":
                data["stages"][st]["status"] = "STALE"
        data["current_stage"] = STAGE_ORDER[first_stale_idx]
        save_state(state_file, data)
        print(f"[StateManager] 已将 {STAGE_ORDER[first_stale_idx]} 及下游阶段标记为 STALE，需重跑。")
        return 2

    print("[StateManager] 所有已通过阶段产物 MD5 校验一致，无失效。")
    return 0


def cmd_add_decision(args: argparse.Namespace) -> int:
    workdir = Path(args.workdir).resolve()
    _, log_file, _ = state_paths(workdir)

    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "stage": args.stage,
        "author": args.author,
        "impact_stages": args.impact or [args.stage],
        "rule": args.rule.strip(),
    }
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[StateManager] 已写入决策账本 ({args.stage}): {entry['rule']}")
    return 0


def cmd_pack_handoff(args: argparse.Namespace) -> int:
    """
    为目标子 Agent 生成严格不超过 50 行的上下文压缩交接单 (state/handoff_brief.md)。
    严禁写入终端日志、中间试错过程，只保留锁定事实、产物指针与相关决策。
    """
    workdir = Path(args.workdir).resolve()
    state_file, log_file, brief_file = state_paths(workdir)
    data = load_state(state_file)
    target = args.target_stage

    # 读取与目标阶段相关的决策条目
    decisions = []
    if log_file.is_file():
        for line in log_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if target in item.get("impact_stages", []) or "ALL" in item.get("impact_stages", []):
                decisions.append(f"- [{item['author']}] {item['rule']}")

    # 收集已通过阶段的唯一产物指针
    passed_artifacts = []
    for st in STAGE_ORDER:
        st_obj = data["stages"][st]
        if st_obj["status"] == "PASSED":
            for art in st_obj.get("artifacts", {}):
                passed_artifacts.append(f"- {st}: `{art}`")

    lines = [
        f"# Handoff Brief · {data['project_id']} -> {target}",
        f"- 生成时间: {datetime.now().isoformat(timespec='seconds')}",
        f"- 能力等级: **{data['capability_level']}** | 目标角色: `{STAGE_OWNER.get(target, 'orchestrator')}`",
        "",
        "## 1. 上游已锁定产物（唯一事实来源，禁止猜数）",
        *(passed_artifacts or ["- （尚无上游产物）"]),
        "",
        "## 2. 本阶段必须遵守的关键决策（来自 decision_log.jsonl）",
        *(decisions[-15:] or ["- （无特殊追加约束）"]),
        "",
        "## 3. 执行纪律",
        "- 仅读取上述锁定产物与本角色卡，严禁读取历史会话日志或已作废初稿。",
        "- 完成后必须调用 `00_state_manager.py checkpoint` 登记产物并释放上下文。",
    ]

    if len(lines) > MAX_HANDOFF_LINES:
        lines = lines[: MAX_HANDOFF_LINES - 1] + ["- （已截断：请严格控制交接单在 50 行内）"]

    brief_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[StateManager] 已生成压缩交接单 ({len(lines)}/{MAX_HANDOFF_LINES} 行): {brief_file}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="lightingdesign v2.0 多 Agent 状态机与上下文压缩工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="初始化状态机")
    p_init.add_argument("--workdir", required=True)
    p_init.add_argument("--project-id", required=True)
    p_init.set_defaults(func=cmd_init)

    p_cp = sub.add_parser("checkpoint", help="登记阶段完成与产物 MD5")
    p_cp.add_argument("--workdir", required=True)
    p_cp.add_argument("--stage", required=True, choices=STAGE_ORDER)
    p_cp.add_argument("--status", required=True, choices=["RUNNING", "PASSED", "FAILED", "RETRY"])
    p_cp.add_argument("--artifact", action="append", help="相对或绝对产物路径，可多次传入")
    p_cp.add_argument("--capability-level", choices=["L1", "L2", "L3"])
    p_cp.add_argument("--force", action="store_true", help="v2.1：跳过前序门禁（必须配 --force-reason）")
    p_cp.add_argument("--force-reason", default="", help="跳过门禁的原因（写入决策账本）")
    p_cp.set_defaults(func=cmd_checkpoint)

    p_stale = sub.add_parser("check-stale", help="检查上游产物变更并传播失效状态")
    p_stale.add_argument("--workdir", required=True)
    p_stale.set_defaults(func=cmd_check_stale)

    p_dec = sub.add_parser("add-decision", help="向防失忆账本追加一条人工/关键决策")
    p_dec.add_argument("--workdir", required=True)
    p_dec.add_argument("--stage", required=True)
    p_dec.add_argument("--author", default="user")
    p_dec.add_argument("--impact", nargs="+", help="受影响的阶段列表，或写 ALL")
    p_dec.add_argument("--rule", required=True)
    p_dec.set_defaults(func=cmd_add_decision)

    p_pack = sub.add_parser("pack-handoff", help="生成 <=50 行的上下文压缩交接单")
    p_pack.add_argument("--workdir", required=True)
    p_pack.add_argument("--target-stage", required=True, choices=STAGE_ORDER)
    p_pack.set_defaults(func=cmd_pack_handoff)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
