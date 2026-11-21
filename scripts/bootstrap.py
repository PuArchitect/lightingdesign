#!/usr/bin/env python3
"""环境自举：扫描本机 → 补齐缺失组件 → 复验 → 出报告。

为什么需要这一步：
  本技能依赖 Radiance（oconv/rtrace/rpict）才能做到 L3。
  同事的电脑上通常没有它。好消息是不需要装任何应用、不需要管理员权限：
  `pyradiance` 的 wheel 自带 Windows 预编译二进制，pip 装完即可用。

三种用法：
  python scripts/bootstrap.py              # 只体检，不装（默认，最安全）
  python scripts/bootstrap.py --install    # 缺什么装什么（需网络）
  python scripts/bootstrap.py --install --offline   # 用本目录 wheels/ 离线装

产出：
  bootstrap_report.md   人看的：装了什么、还缺什么、下一步怎么配
  capabilities.json     机器读的：级别 L1/L2/L3

退出码：0 已就绪 / 1 仍缺（看报告）/ 2 无法自举（如没有 pip）
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
WHEELS = REPO / "wheels"

# pip 包名 -> (import 名, 用途, 是否必需)
PKGS = [
    ("pillow", "PIL", "出图（伪彩图版）", True),
    ("openpyxl", "openpyxl", "xlsx 读写（材料表/灯具表）", True),
    ("numpy", "numpy", "数值计算", True),
    ("python-docx", "docx", "docx 报告", False),
    ("pyradiance", "pyradiance", "Radiance 内核（含 oconv/rtrace/rpict）", False),
    ("rhino3dm", "rhino3dm", "直接读 3dm 模型", False),
    ("ezdxf", "ezdxf", "解析 DXF 图纸", False),
]

RAD_BINS = ["oconv", "rtrace", "rpict"]


def _run(cmd: list[str], timeout: int = 300) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except FileNotFoundError:
        return 127, "not found"
    except Exception as e:  # noqa: BLE001
        return 1, f"{type(e).__name__}: {e}"


def has_module(name: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def find_radiance() -> dict:
    """找 oconv/rtrace/rpict：PATH → RAYPATH → pyradiance 自带 bin。"""
    cands = []
    raypath = os.environ.get("RAYPATH", "")
    for d in [x for x in raypath.split(os.pathsep) if x]:
        cands.append(Path(d))
    try:
        import pyradiance
        cands.append(Path(pyradiance.__file__).parent / "bin")
    except Exception:
        pass
    for base in sys.path:
        p = Path(base) / "pyradiance" / "bin"
        if p.is_dir():
            cands.append(p)

    found = {}
    for b in RAD_BINS:
        path = None
        for d in cands:
            for name in (b, f"{b}.exe"):
                f = d / name
                if f.exists():
                    path = str(f)
                    break
            if path:
                break
        if not path:
            import shutil
            path = shutil.which(b) or shutil.which(f"{b}.exe")
        found[b] = path

    bindir = str(Path(found["oconv"]).parent) if found.get("oconv") else None
    libdir = None
    if bindir:
        cand = Path(bindir).parent / "lib"
        if cand.is_dir():
            libdir = str(cand)
    return {"bins": found, "bindir": bindir, "libdir": libdir,
            "ready": all(found.get(b) for b in RAD_BINS)}


def raypath_hint(paths: dict) -> str:
    if not paths.get("bindir"):
        return ""
    parts = [paths["bindir"]]
    if paths.get("libdir"):
        parts.append(paths["libdir"])
    parts.append(".")
    joined = os.pathsep.join(parts)
    if os.name == "nt":
        return (f"PowerShell：$env:RAYPATH = \"{joined}\"\n"
                f"cmd.exe   ：set RAYPATH={joined}\n"
                f"git-bash  ：export RAYPATH=\"{joined}\"   # 用 ; 分隔需引号\n"
                f"永久生效  ：setx RAYPATH \"{joined}\"")
    return f"bash/zsh：export RAYPATH=\"{joined}\""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true", help="缺什么装什么")
    ap.add_argument("--offline", action="store_true", help="从 wheels/ 离线安装")
    ap.add_argument("--yes", action="store_true", help="跳过确认")
    ap.add_argument("--pkgs", default=None,
                    help="只装指定包（逗号分隔），便于弱平台分批、规避 60 s 超时")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    py_ok = sys.version_info >= (3, 8)
    print(f"Python {sys.version.split()[0]}  ({sys.executable})")
    if not py_ok:
        print("!! 需要 Python 3.8+，请先安装 Python。")
        return 2

    rows = []          # (组件, 状态, 动作, 结果)
    to_install = []

    for pip_name, imp_name, use, required in PKGS:
        ok = has_module(imp_name)
        rows.append({"pip": pip_name, "imp": imp_name, "use": use,
                     "required": required, "present": ok, "action": "-", "result": "-"})
        if not ok:
            to_install.append(pip_name)

    rad = find_radiance()
    print(f"Radiance: {'已就绪' if rad['ready'] else '缺失'}")
    if rad.get("bindir"):
        print(f"  bin: {rad['bindir']}")

    # 分批安装：弱平台按 60 s 拆批，一次只装几个包
    if args.pkgs:
        want = {p.strip().replace("_", "-").lower()
                for p in args.pkgs.split(",") if p.strip()}
        skipped = [p for p in to_install if p.lower() not in want]
        to_install = [p for p in to_install if p.lower() in want]
        if skipped:
            print(f"按 --pkgs 跳过: {', '.join(skipped)}（下次再装）")

    # ---- 是否安装
    if to_install and args.install:
        if not args.yes:
            print(f"\n将安装: {', '.join(to_install)}")
            print("确认请加 --yes")
            return 1
        rc, out = _run([sys.executable, "-m", "pip", "--version"], 60)
        if rc != 0:
            print("!! 没有可用的 pip，无法自举。请先修复 pip 或用离线 wheels。")
            return 2

        base = [sys.executable, "-m", "pip", "install"]
        if args.offline:
            base += ["--no-index", "--find-links", str(WHEELS)]
        else:
            base += ["--disable-pip-version-check"]

        for pkg in to_install:
            row = next(r for r in rows if r["pip"] == pkg)
            # 先试 --user（免管理员），失败再试普通安装（适配虚拟环境）
            rc, out = _run(base + ["--user", pkg])
            if rc != 0:
                rc, out = _run(base + [pkg])
            row["action"] = "install" + ("(offline)" if args.offline else "")
            row["result"] = "OK" if rc == 0 else f"FAIL rc={rc}: {out.strip()[-160:]}"
            print(f"  {pkg:<14} {'OK' if rc == 0 else 'FAIL'}")
            # 装完复验
            if rc == 0:
                import importlib
                importlib.invalidate_caches()
                row["present"] = has_module(row["imp"])

    # ---- 复验
    for r in rows:
        if r["action"] == "-":
            r["result"] = "已存在" if r["present"] else "缺失（未安装）"

    rad = find_radiance()          # 装完再找一次

    # ---- 定级
    have = {r["imp"]: r["present"] for r in rows}
    # L3 需要 numpy：单位贡献率 / 线性反推都依赖它，文档与定级必须一致
    if (rad["ready"] and have.get("PIL") and have.get("openpyxl")
            and have.get("numpy")):
        level, why = "L3", "可做辐射计算 + 图版 + 表格 + 报告"
    elif have.get("PIL") and have.get("openpyxl"):
        level, why = "L2", "无 Radiance 或缺 numpy：只能直射估算，报告须标 _L2"
    else:
        level, why = "L1", "缺关键库：只能出模板与人工填表，报告须标 _L1"

    # ---- 写报告
    lines = [
        "# 环境自举报告",
        "",
        f"- Python：{sys.version.split()[0]}（`{sys.executable}`）",
        f"- 级别：**{level}** —— {why}",
        f"- 操作模式：{'安装' if args.install else '仅体检'}"
        + ("（离线）" if args.offline else ""),
        "",
        "## 组件",
        "",
        "| 组件 | 用途 | 必需 | 状态 | 动作 | 结果 |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['pip']} | {r['use']} | {'是' if r['required'] else '否'} | "
                     f"{'✅ 有' if r['present'] else '❌ 缺'} | {r['action']} | {r['result']} |")
    lines += ["", "## Radiance", ""]
    for b in RAD_BINS:
        lines.append(f"- `{b}`：{rad['bins'].get(b) or '**未找到**'}")
    if rad["ready"]:
        lines += ["", "配置环境变量（Radiance 不配 RAYPATH 会给出**看似合理的错值**）：",
                  "", "```", raypath_hint(rad), "```"]
    else:
        lines += ["", "装 `pyradiance` 可获得 Windows 预编译二进制（无需管理员权限）：",
                  "", "```",
                  "python scripts/bootstrap.py --install --yes",
                  "```"]

    lines += ["", "## 下一步", ""]
    if level == "L3":
        lines.append("直接进入 `SKILL.md` 阶段①：交接清单。")
    elif level == "L2":
        lines.append("可按 L2 开始（材料表/灯具表/报告），**报告封面必须标 `_L2`**。")
        lines.append("要升 L3：`python scripts/bootstrap.py --install --yes`")
    else:
        lines.append("只能用 `templates/` 手工填表，**报告封面必须标 `_L1`**。")
        lines.append("先从 `wheels/` 离线安装，或让 IT 配好 Python 环境。")

    (REPO / "bootstrap_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ---- 更新 capabilities.json
    cap = {
        "level": level, "reason": why,
        "python": {"version": sys.version.split()[0], "executable": sys.executable},
        "modules": {r["imp"]: {"available": r["present"], "use": r["use"]} for r in rows},
        "radiance": {"ready": rad["ready"], "bins": rad["bins"],
                     "bindir": rad["bindir"], "libdir": rad["libdir"]},
        "raypath": raypath_hint(rad),
        "installed": [r["pip"] for r in rows if r["action"].startswith("install")],
        "still_missing": [r["pip"] for r in rows if not r["present"]],
    }
    (REPO / "capabilities.json").write_text(json.dumps(cap, ensure_ascii=False, indent=1),
                                            encoding="utf-8")

    print(f"\n级别 {level} —— {why}")
    miss = [r["pip"] for r in rows if not r["present"] and r["required"]]
    if miss:
        print(f"仍缺必需项: {', '.join(miss)}")
    print("报告: bootstrap_report.md")
    return 0 if level == "L3" else 1


if __name__ == "__main__":
    raise SystemExit(main())
