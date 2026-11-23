#!/usr/bin/env python3
"""
Stage 3: Radiance 物理防呆与闭合审计核心库 (lightingdesign v2.0)
严禁在业务脚本中手写 179/pi 换算或直接 import 上游内存变量，所有计算必须调用本模块并落盘 JSON。
"""

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Iterable

RADIANCE_WHITE_EFFICACY = 179.0
DEFAULT_LED_SYSTEM_EFFICACY = 110.0


def cd_m2_to_radiance(luminance_cd_m2: float) -> float:
    """
    将目标表面光度亮度 (cd/m^2) 换算为 Radiance 辐亮度 (W/m^2/sr)。
    铁律: L_cd_m2 = 179 * R_rad，严禁除以 pi。
    """
    if luminance_cd_m2 < 0:
        raise ValueError(f"亮度不能为负: {luminance_cd_m2}")
    return luminance_cd_m2 / RADIANCE_WHITE_EFFICACY


def lambertian_flux_to_radiance(lumens: float, emitting_area_m2: float) -> float:
    """
    将朗伯发光面总光通量 (lm) 换算为 Radiance 辐亮度 (W/m^2/sr)。
    公式: L = Flux / (pi * Area), R = L / 179
    """
    if lumens < 0:
        raise ValueError(f"光通量不能为负: {lumens}")
    if emitting_area_m2 <= 1e-6:
        raise ValueError(f"发光面积异常过小或非正: {emitting_area_m2} m^2")
    luminance_cd_m2 = lumens / (math.pi * emitting_area_m2)
    return cd_m2_to_radiance(luminance_cd_m2)


@dataclass(frozen=True)
class CoveRect:
    """
    强类型矩形灯槽边界，禁止使用裸 4 元组 (x0, y0, x1, y1) 防止解包顺序错位。
    单位: 米 (m)
    """
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z: float
    strip_width_m: float

    def __post_init__(self) -> None:
        if self.x_max <= self.x_min:
            raise ValueError(f"灯槽 X 坐标非法: x_min={self.x_min}, x_max={self.x_max}")
        if self.y_max <= self.y_min:
            raise ValueError(f"灯槽 Y 坐标非法: y_min={self.y_min}, y_max={self.y_max}")
        if self.strip_width_m <= 0:
            raise ValueError(f"灯带宽度必须 > 0: {self.strip_width_m}")

    @property
    def perimeter_m(self) -> float:
        return 2.0 * ((self.x_max - self.x_min) + (self.y_max - self.y_min))

    @property
    def emitting_area_m2(self) -> float:
        return self.perimeter_m * self.strip_width_m


def audit_shell_materials(
    shell_materials: Iterable[str],
    raw_model_materials: Iterable[str],
) -> dict:
    """
    壳体材质审计：断言计算壳体仅使用受控材质名，与未识别的原始模型材质交集为空。
    """
    shell_set = set(shell_materials)
    raw_set = set(raw_model_materials)
    leaked = sorted(shell_set & raw_set)
    result = {
        "passed": len(leaked) == 0,
        "shell_material_count": len(shell_set),
        "leaked_raw_materials": leaked,
    }
    if not result["passed"]:
        raise RuntimeError(
            f"[壳体材质审计 FAIL] 发现未受控的原始模型材质进入计算壳: {leaked}"
        )
    return result


def audit_material_mapping(raw_model_materials: Iterable[str], mapping_table: dict) -> dict:
    """
    v2.1 推荐判据（替代「交集为空」的代理判据）：
    房间内出现的每一种原始模型材质，都必须在 mapping_table 中有记录（含反射率与置信度）。
    返回未映射清单；有任何未映射即 FAIL。
    """
    raw = sorted({m for m in raw_model_materials if m})
    missing = [m for m in raw if m not in mapping_table]
    result = {
        "passed": len(missing) == 0,
        "raw_material_count": len(raw),
        "mapped_count": len(raw) - len(missing),
        "missing_materials": missing,
    }
    if missing:
        raise RuntimeError(f"[材质映射审计 FAIL] 房间内存在未映射材质: {missing}")
    return result


def verify_closure(
    main_avg_lx: float,
    single_source_contributions: dict[str, float],
    threshold_pct: float = 1.0,
) -> dict:
    """
    闭合校验：校验逐光源独立计算之和与全场景主计算的偏差。
    若偏差超过 threshold_pct (默认 1.0%)，立即报错中止，防止脚本参数不同源。
    """
    if main_avg_lx <= 0:
        raise ValueError(f"主计算平均照度必须 > 0，当前为: {main_avg_lx}")

    sum_single_lx = sum(single_source_contributions.values())
    diff_lx = sum_single_lx - main_avg_lx
    diff_pct = abs(diff_lx) / main_avg_lx * 100.0
    passed = diff_pct <= threshold_pct

    report = {
        "passed": passed,
        "main_avg_lx": round(main_avg_lx, 2),
        "sum_single_sources_lx": round(sum_single_lx, 2),
        "diff_lx": round(diff_lx, 2),
        "diff_pct": round(diff_pct, 3),
        "threshold_pct": threshold_pct,
        "contributions_lx": {k: round(v, 2) for k, v in single_source_contributions.items()},
    }
    if not passed:
        raise RuntimeError(
            f"[闭合校验 FAIL] 单源之和 ({sum_single_lx:.2f} lx) 与主计算 ({main_avg_lx:.2f} lx) "
            f"偏差 {diff_pct:.2f}% > 阈值 {threshold_pct}%！请检查各脚本是否同源读取 results.json。"
        )
    return report


def compute_power_and_lpd(
    total_lumens: float,
    room_area_m2: float,
    led_system_efficacy_lm_w: float = DEFAULT_LED_SYSTEM_EFFICACY,
    efficacy_grade: str = "C",
) -> dict:
    """
    明确区分 Radiance 179 lm/W 与真实 LED 系统光效，计算总电功率与 LPD。
    """
    if room_area_m2 <= 0:
        raise ValueError(f"房间面积必须 > 0: {room_area_m2}")
    if led_system_efficacy_lm_w <= 0:
        raise ValueError(f"LED 系统光效必须 > 0: {led_system_efficacy_lm_w}")

    total_power_w = total_lumens / led_system_efficacy_lm_w
    lpd_w_m2 = total_power_w / room_area_m2
    return {
        "total_lumens": round(total_lumens, 1),
        "led_system_efficacy_lm_w": led_system_efficacy_lm_w,
        "efficacy_assumption_grade": efficacy_grade,
        "total_power_w": round(total_power_w, 2),
        "room_area_m2": round(room_area_m2, 2),
        "lpd_w_m2": round(lpd_w_m2, 2),
    }


def save_ssot_results(results: dict, out_path: Path) -> None:
    """将最终标定结果落盘为单一数据源 (SSOT)，供制图/表格/报告/审计统一读取。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
