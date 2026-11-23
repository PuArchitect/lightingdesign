# -*- coding: utf-8 -*-
"""一致性审计：三份技能副本（v2.1 / wb / installed）的版本、六类图、提示词、过期引用。"""
import argparse
import re
from pathlib import Path

DEFAULT = [
    Path(r"D:\DeepSeekHarness\documents\lighting develop\research\result loop\lightingdesign_v2.1"),
    Path(r"D:\DeepSeekHarness\documents\lighting develop\research\result loop\lightingdesign_v2.1_wb"),
    Path(r"C:\Users\tiany\.workbuddy\skills\lightingdesign"),
]
STALE = [r"五类", r"2\.2\.1", r"36 项", r"9 页设计版"]


def check(p: Path):
    row = {"path": str(p), "exists": p.exists()}
    if not p.exists():
        return row
    skill = (p / "SKILL.md").read_text(encoding="utf-8")
    m = re.search(r"^version:\s*(\S+)", skill, re.M)
    row["version"] = m.group(1) if m else "?"
    six = "六类图" in (p / "scripts" / "06_preflight_delivery.py").read_text(encoding="utf-8")
    row["six_types"] = six
    row["tester_prompt"] = (p / "PROMPTS" / "开跑_测试项目_复制这段.md").exists()
    stale = []
    for f in ["SKILL.md", "agents/03_designer.md", "PROMPTS/03_designer.md",
              "PROMPTS/WORKBUDDY_RUNBOOK.md", "README.md", "MERGE_NOTES.md"]:
        fp = p / f
        if not fp.exists():
            continue
        txt = fp.read_text(encoding="utf-8")
        for pat in STALE:
            if re.search(pat, txt):
                stale.append(f"{f}:{pat}")
    row["stale"] = stale
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", nargs="*", default=[str(x) for x in DEFAULT])
    args = ap.parse_args()
    rows = [check(Path(x)) for x in args.paths]
    bad = 0
    for r in rows:
        print(f"\n{r['path']}")
        if not r["exists"]:
            print("  MISSING"); bad += 1; continue
        print(f"  version={r['version']}  six_types={r['six_types']}  tester_prompt={r['tester_prompt']}")
        if r["stale"]:
            bad += 1
            print("  stale:", ", ".join(r["stale"][:8]))
        else:
            print("  stale: none")
    # 版本一致
    versions = {r.get("version") for r in rows if r.get("exists")}
    if len(versions) > 1:
        print("\n版本不一致:", versions)
        bad += 1
    else:
        print("\n版本一致:", versions)
    print("审计结果:", "PASS" if bad == 0 else f"FAIL（{bad} 处）")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
