#!/usr/bin/env python3
"""能力探针：判断当前环境能跑到哪一级（L1/L2/L3）。

设计原则：
  · 只用标准库，任何 Python 3.8+ 都能跑
  · 不安装任何东西，只探测
  · 输出 capabilities.json，供 Agent 与后续脚本读取
  · 结论宁可保守：探不到就当没有

用法：
  python scripts/capability_probe.py [--out capabilities.json]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import sys
from pathlib import Path

# 模块名 -> 用途
PY_MODULES = {
    "numpy": "数值计算",
    "PIL": "出图（伪彩/图版）",
    "openpyxl": "xlsx 读写",
    "docx": "docx 报告",
    "rhino3dm": "3dm 直接读取",
    "ezdxf": "DXF 解析",
    "pymupdf": "PDF 渲染与向量提取",
}

# 可执行文件（多个候选名）
BINARIES = {
    "oconv": ["oconv"],
    "rtrace": ["rtrace"],
    "rpict": ["rpict"],
    "ra_tiff": ["ra_tiff"],
    "evalglare": ["evalglare"],
}


def has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def find_bin(names: list[str]) -> str | None:
    # 1) PATH
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    # 2) RAYPATH 里找
    raypath = os.environ.get("RAYPATH", "")
    for d in [x for x in raypath.split(os.pathsep) if x]:
        for n in names:
            for cand in (Path(d) / n, Path(d) / f"{n}.exe"):
                if cand.exists():
                    return str(cand)
    # 3) pyradiance 自带 bin（常见安装位置）
    for base in sys.path:
        b = Path(base) / "pyradiance" / "bin"
        if b.is_dir():
            for n in names:
                for cand in (b / n, b / f"{n}.exe"):
                    if cand.exists():
                        return str(cand)
    return None


def probe() -> dict:
    mods = {m: {"available": has_module(m), "use": u} for m, u in PY_MODULES.items()}
    bins = {k: find_bin(v) for k, v in BINARIES.items()}

    radiance_ok = all(bins.get(k) for k in ("oconv", "rtrace"))
    plot_ok = mods["PIL"]["available"]
    sheet_ok = mods["openpyxl"]["available"]
    doc_ok = mods["docx"]["available"]

    if radiance_ok and plot_ok and sheet_ok:
        level = "L3"
        reason = "可做辐射计算 + 图版 + 表格 + 报告"
    elif plot_ok and sheet_ok:
        level = "L2"
        reason = "无 Radiance：只做直射估算与表格图版，报告须标 _L2"
    else:
        level = "L1"
        reason = "缺关键库：只能出模板与人工填表，报告须标 _L1"

    missing = [m for m, v in mods.items() if not v["available"]]
    missing_bins = [k for k, v in bins.items() if not v]
    if not doc_ok:
        missing.append("docx(报告将无法自动生成)")

    return {
        "level": level,
        "reason": reason,
        "python": {
            "version": platform.python_version(),
            "executable": sys.executable,
            "platform": platform.platform(),
        },
        "modules": mods,
        "binaries": bins,
        "radiance_ready": radiance_ok,
        "missing_modules": missing,
        "missing_binaries": missing_bins,
        "advice": _advice(level, missing, missing_bins),
    }


def _advice(level: str, missing: list[str], missing_bins: list[str]) -> list[str]:
    out = []
    if level == "L1":
        out.append("先装 openpyxl 与 Pillow（pip install openpyxl pillow），即可升到 L2")
    if level == "L2":
        out.append("装 Radiance 或 pyradiance 可升到 L3；在此之前报告封面必须标 _L2")
        out.append("L2 下不要引用 -ab/-ad 等收敛参数，也不要做眩光计算")
    if level == "L3":
        out.append("完整能力：可做逐点照度、眩光、真实网格")
        out.append("注意 RAYPATH 需同时含 bin 与 lib，否则 rtrace 会给出看似合理的错值")
    if "rhino3dm" in missing:
        out.append("无 rhino3dm：3dm 无法直接读，改用甲方导出的 OBJ/网格")
    if "ezdxf" in missing:
        out.append("无 ezdxf：DWG/DXF 需先转成 PDF 或让甲方导出")
    return out


def main() -> int:
    # 弱终端（Windows cp936 控制台）打印中文会抛 UnicodeEncodeError，
    # 这里直接把 stdout 重配成 utf-8，失败也不影响 JSON 落盘。
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("capabilities.json"))
    args = ap.parse_args()

    cap = probe()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(cap, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"级别: {cap['level']}  —— {cap['reason']}")
    print(f"Python: {cap['python']['version']}")
    ok = [m for m, v in cap["modules"].items() if v["available"]]
    print(f"可用模块: {', '.join(ok) if ok else '无'}")
    if cap["missing_modules"]:
        print(f"缺失模块: {', '.join(cap['missing_modules'])}")
    if cap["missing_binaries"]:
        print(f"缺失可执行: {', '.join(cap['missing_binaries'])}")
    for a in cap["advice"]:
        print(f"  · {a}")
    print(f"\n已写入 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
