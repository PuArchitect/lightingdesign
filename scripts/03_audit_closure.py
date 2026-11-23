#!/usr/bin/env python3
"""
Stage 3: 独立闭合校验与逐光源贡献审计 (lightingdesign v2.0)
用法: python 03_audit_closure.py --results results.json --out closure_audit.json
"""

import argparse
import json
import sys
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec

_core_path = Path(__file__).resolve().parent / "02_rad_core.py"
_spec = spec_from_file_location("rad_core", _core_path)
rad_core = module_from_spec(_spec)  # type: ignore
_spec.loader.exec_module(rad_core)  # type: ignore


def run_closure_audit(results_path: Path, out_path: Path, threshold_pct: float = 1.0) -> int:
    data = json.loads(results_path.read_text(encoding="utf-8"))

    main_avg_lx = float(data["workplane_usable"]["avg_lx"])
    contributions = {k: float(v) for k, v in data["single_source_contributions_lx"].items()}

    try:
        report = rad_core.verify_closure(main_avg_lx, contributions, threshold_pct=threshold_pct)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    total = report["sum_single_sources_lx"]
    report["share_pct"] = {
        k: round((v / total) * 100.0, 1) if total > 0 else 0.0
        for k, v in contributions.items()
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"[Stage 3] 闭合校验 PASS: 主计算 {report['main_avg_lx']} lx vs "
        f"单源之和 {report['sum_single_sources_lx']} lx (偏差 {report['diff_pct']}%)"
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 3 闭合校验")
    parser.add_argument("--results", required=True, help="results.json 路径")
    parser.add_argument("--out", default="closure_audit.json", help="审计报告输出路径")
    parser.add_argument("--threshold", type=float, default=1.0, help="允许最大偏差百分比")
    args = parser.parse_args()
    sys.exit(run_closure_audit(Path(args.results), Path(args.out), args.threshold))
