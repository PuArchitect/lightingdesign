#!/usr/bin/env python3
"""
Stage 0: 环境指纹采集与能力定级门禁 (lightingdesign v2.1)
v2.1 修改：
  1) 工作目录回退：C:\\Temp 不可用时依次回退 tempfile.gettempdir() / 当前目录下的 ld_tmp；
  2) Radiance 冒烟测试：用 1x1 m 发光面 + rtrace 校验，防止 RAYPATH 坏了却判 L3（v1 的静默失败）；
  3) 输出 RAYPATH 与可复用的 radiance_env，供下游脚本直接使用；
  4) 半径/依赖判定与 v2.0 保持兼容。
用法: python 00_preflight_env.py --project-id room4 --out env_fingerprint.json
"""

import argparse
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REQUIRED_L2_PACKAGES = ["numpy", "Pillow", "pymupdf", "openpyxl"]
OPTIONAL_PACKAGES = ["rhino3dm", "ezdxf", "python-docx", "pyradiance", "jsonschema"]
RADIANCE_BINS = ["oconv", "rtrace", "rpict"]
SMOKE_EXPECTED = 2.176   # 1x1 m 发光面(radiance=5) 在正下方 1 m 处的辐照度，本仓库标定值
SMOKE_TOL = 0.05         # ±5%


def get_pkg_version(pkg_name: str):
    try:
        return importlib.metadata.version(pkg_name)
    except importlib.metadata.PackageNotFoundError:
        return None


def find_radiance():
    """返回 (bins: dict, bin_dir: str|None, lib_dir: str|None)。"""
    bin_dir = lib_dir = None
    try:
        import pyradiance  # type: ignore
        root = Path(pyradiance.__file__).resolve().parent
        if (root / "bin").is_dir():
            bin_dir = str(root / "bin")
        if (root / "lib").is_dir():
            lib_dir = str(root / "lib")
    except ImportError:
        pass
    search = os.pathsep.join([d for d in [bin_dir, os.environ.get("PATH", "")] if d])
    found = {b: shutil.which(b, path=search) for b in RADIANCE_BINS}
    return found, bin_dir, lib_dir


def build_radiance_env(bin_dir, lib_dir):
    parts = [p for p in [bin_dir, lib_dir, "."] if p]
    return {"RAYPATH": ";".join(parts) if platform.system() == "Windows" else ":".join(parts)}


def radiance_smoke(bins, bin_dir, lib_dir, workroot: Path):
    """真实跑一次 oconv+rtrace，返回 (ok, detail, value)。"""
    if not all(bins.values()) or not bin_dir:
        return False, "Radiance 二进制不完整", None
    env = dict(os.environ, **build_radiance_env(bin_dir, lib_dir))
    d = workroot / "radiance_smoke"
    d.mkdir(parents=True, exist_ok=True)
    rad = d / "smoke.rad"
    rad.write_text(
        "void light src\n0\n0\n3 5 5 5\n\n"
        "src polygon p\n0\n0\n12\n"
        "0 0 1  0 1 1  1 1 1  1 0 1\n",
        encoding="utf-8",
    )
    try:
        r1 = subprocess.run([bins["oconv"], str(rad)], capture_output=True, env=env, cwd=str(d), timeout=30)
        if r1.returncode != 0 or not r1.stdout:
            return False, f"oconv 失败: {r1.stderr.decode('utf-8', 'ignore')[:200]}", None
        oct_ = d / "smoke.oct"
        oct_.write_bytes(r1.stdout)
        r2 = subprocess.run([bins["rtrace"], "-I", "-h", "-ab", "0", str(oct_)],
                            input=b"0 0 0 0 0 1\n", capture_output=True, env=env, cwd=str(d), timeout=30)
        if r2.returncode != 0:
            return False, f"rtrace 失败: {r2.stderr.decode('utf-8', 'ignore')[:200]}", None
        val = float(r2.stdout.split()[0])
        # v1 的典型静默失败：RAYPATH 缺 lib 时每条光线返回 1,1,1
        if abs(val - 1.0) < 1e-6:
            return False, "rtrace 返回 1,1,1（RAYPATH 缺 lib 的典型静默失败）", val
        ok = abs(val - SMOKE_EXPECTED) / SMOKE_EXPECTED <= SMOKE_TOL
        return ok, f"{val:.4f} W/m2（标定 {SMOKE_EXPECTED} ±{SMOKE_TOL:.0%}）", val
    except Exception as e:
        return False, f"冒烟测试异常: {e}", None


def ensure_ascii_workdir(project_id: str):
    safe = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in project_id)
    candidates = []
    if platform.system() == "Windows":
        candidates.append(Path(r"C:\Temp"))
    candidates.append(Path(tempfile.gettempdir()))
    candidates.append(Path.cwd() / "ld_tmp")
    for base in candidates:
        try:
            wd = base / f"ld_{safe}"
            wd.mkdir(parents=True, exist_ok=True)
            probe = wd / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return str(wd), None
        except Exception as e:
            last = e
            continue
    return None, f"无可写工作目录（最后错误: {last}）"


def find_headless_browser():
    candidates = [
        shutil.which("chrome"), shutil.which("msedge"), shutil.which("google-chrome"), shutil.which("chromium"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for p in candidates:
        if p and Path(p).is_file():
            return str(Path(p).resolve())
    return None


def check_cjk_fonts():
    cands = [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\simhei.ttf",
             "/System/Library/Fonts/PingFang.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
    return [f for f in cands if Path(f).is_file()]


def run_preflight(project_id: str, out_path: Path) -> int:
    exe = str(Path(sys.executable).resolve())
    alias = "WindowsApps" in exe
    packages = {p: get_pkg_version(p) for p in REQUIRED_L2_PACKAGES + OPTIONAL_PACKAGES}
    bins, bin_dir, lib_dir = find_radiance()
    rad_ready = all(bins.values())
    ascii_wd, wd_err = ensure_ascii_workdir(project_id)
    browser = find_headless_browser()
    fonts = check_cjk_fonts()

    smoke_ok, smoke_detail, smoke_val = (False, "未执行", None)
    if rad_ready and ascii_wd:
        smoke_ok, smoke_detail, smoke_val = radiance_smoke(bins, bin_dir, lib_dir, Path(ascii_wd))

    missing_l2 = [p for p in REQUIRED_L2_PACKAGES if packages[p] is None]
    if missing_l2 or not ascii_wd:
        level = "BLOCKED"
    elif rad_ready and smoke_ok:
        level = "L3"
    else:
        level = "L2"

    warnings = []
    if alias:
        warnings.append("检测到 WindowsApps Python 别名，请切换真实 Python。")
    if not rad_ready:
        warnings.append("Radiance 二进制不完整，能力锁定 L2。")
    if rad_ready and not smoke_ok:
        warnings.append(f"Radiance 冒烟测试未通过（{smoke_detail}），能力锁定 L2——这通常意味着 RAYPATH 配置错误。")
    if not browser:
        warnings.append("未检测到 Chrome/Edge，Stage 5/6 的无头打印与视觉质检不可用。")
    if not fonts:
        warnings.append("未检测到常见中文字体，PDF 可能掉字。")
    if wd_err:
        warnings.append(wd_err)

    fingerprint = {
        "schema_version": "2.1",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "os": platform.platform(),
        "python_executable": exe,
        "python_version": platform.python_version(),
        "is_ms_store_alias": alias,
        "packages": packages,
        "radiance_bins": bins,
        "radiance_bin_dir": bin_dir,
        "radiance_lib_dir": lib_dir,
        "raypath": build_radiance_env(bin_dir, lib_dir).get("RAYPATH", ""),
        "raypath_env_original": os.environ.get("RAYPATH", ""),
        "radiance_env": build_radiance_env(bin_dir, lib_dir),
        "radiance_smoke": {"passed": smoke_ok, "detail": smoke_detail, "value": smoke_val},
        "headless_browser": browser,
        "cjk_fonts_found": fonts,
        "ascii_workdir": ascii_wd,
        "capability_level": level,
        "visual_qc_ready": bool(browser and packages["pymupdf"] and packages["Pillow"]),
        "missing_l2_packages": missing_l2,
        "warnings": warnings,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(fingerprint, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Stage 0] 能力判定: {level} | 视觉自检就绪: {fingerprint['visual_qc_ready']}")
    print(f"[Stage 0] Radiance 冒烟: {smoke_detail}")
    print(f"[Stage 0] 英文隔离目录: {ascii_wd}")
    for w in warnings:
        print(f"  [WARN] {w}")
    if level == "BLOCKED":
        print(f"  [FAIL] 缺少基础依赖或工作目录不可写: {missing_l2}")
        return 1
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Stage 0 环境指纹与能力定级 (v2.1)")
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--out", default="env_fingerprint.json")
    args = ap.parse_args()
    sys.exit(run_preflight(args.project_id, Path(args.out)))
