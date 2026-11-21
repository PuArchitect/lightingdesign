"""通用命名解析器：把任意工作室的材质/图层名解析成光学属性。

设计目标：不写死任何一个工作室的名单。

三层结构：
  L1 通用内核  —— 只看"结构"（材质名首段=物理类型；图层路径含部位关键词）+ 中英关键词兜底
  L2 工作室档案 —— 可选 JSON，补充该工作室的物理类型表与关键词（如 TYARCH 的 WOOD/STONE/PAINT）
  L3 项目覆盖  —— 业主逐行确认的反射率（材料表），优先级最高

关键行为：**解析不了的材质必须报错或报警，绝不静默丢弃**
（本项目曾因跳过 GLASS-* 在墙上开了洞，照度掉 37%）。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONV = ROOT / "data" / "conventions"

# ------------------------------------------------------------------ L1 光学默认值
# 物理类型 -> (R, G, B, specular, roughness, 可信度)
OPTICS = {
    "WOOD":     (0.150, 0.125, 0.100, 0.03, 0.15, "medium"),
    "STONE":    (0.220, 0.215, 0.210, 0.05, 0.12, "medium"),
    "METAL":    (0.300, 0.300, 0.310, 0.35, 0.08, "medium"),
    "PAINT":    (0.480, 0.475, 0.465, 0.03, 0.10, "medium"),
    "GLASS":    (0.080, 0.080, 0.085, 0.30, 0.05, "medium"),
    "FABRIC":   (0.070, 0.065, 0.060, 0.00, 0.25, "medium"),
    "LEATHER":  (0.055, 0.050, 0.045, 0.05, 0.28, "medium"),
    "CARPET":   (0.060, 0.055, 0.050, 0.00, 0.10, "medium"),
    "TILE":     (0.220, 0.215, 0.205, 0.08, 0.10, "medium"),
    "CERAMIC":  (0.400, 0.395, 0.385, 0.10, 0.08, "medium"),
    "CONCRETE": (0.320, 0.315, 0.305, 0.02, 0.15, "medium"),
    "PLASTER":  (0.600, 0.600, 0.580, 0.02, 0.10, "medium"),
    "DEFAULT":  (0.450, 0.445, 0.435, 0.03, 0.12, "low"),
}
# 常见的非标准写法 -> 标准物理类型
ALIAS = {
    "CNCRT": "CONCRETE", "CONC": "CONCRETE",
    "WOODS": "WOOD", "TIMBER": "WOOD",
    "MARBLE": "STONE", "GRANITE": "STONE", "TERRAZZO": "STONE", "TERRA": "STONE",
    "STON": "STONE", "ROCK": "STONE",
    "BRASS": "METAL", "STEEL": "METAL", "IRON": "METAL", "ALU": "METAL",
    "ALUIMINUM": "METAL", "ALUMINIUM": "METAL", "SS": "METAL",
    "MIRROR": "METAL", "CHROME": "METAL",
    "FAB": "FABRIC", "CLOTH": "FABRIC", "TEXTILE": "FABRIC", "LINEN": "FABRIC",
    "SOFA": "LEATHER", "PU": "LEATHER", "SKIN": "LEATHER",
    "RUG": "CARPET", "MOQUETTE": "CARPET",
    "GLS": "GLASS", "ACRYLIC": "GLASS", "PMMA": "GLASS",
    "PT": "PAINT", "LACQUER": "PAINT", "COATING": "PAINT", "FINISH": "PAINT",
    "CER": "CERAMIC", "PORCELAIN": "CERAMIC",
    "PLA": "PLASTER", "GYPSUM": "PLASTER",
}

# 名称修饰词 -> 反射率系数
MODIFIERS = [
    (("black", "黑", "ink", "ebony"), 0.35),
    (("dark", "深", "dark brown"), 0.60),
    (("deep grey", "dark grey", "深灰"), 0.55),
    (("grey", "gray", "灰", "silver"), 0.65),
    (("white", "白", "ivory", "cream"), 1.25),
    (("light", "浅", "pale"), 1.15),
    (("rough", "毛面", "哑", "matte"), 1.00),
]

# 部位关键词（图层路径或材质名里出现即归类）
PART_RULES = [
    ("ceiling", ("天花", "吊顶", "ceiling", "soffit", "ceiling")),
    ("wall", ("墙面", "墙壁", "墙", "wall", "paneling", "饰面墙")),
    ("floor", ("地面", "地板", "楼板", "floor", "carpet", "terrazzo", "踢脚")),
    ("furniture", ("家具", "柜", "沙发", "furniture", "sofa", "chair", "table")),
    ("fixture", ("照明", "灯具", "light", "lamp", "luminaire")),
]


@dataclass
class Resolution:
    name: str
    physical: str
    part: str
    rgb: tuple[float, float, float]
    spec: float
    rough: float
    confidence: str
    source: str
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "name": self.name, "physical": self.physical, "part": self.part,
            "rgb": [round(v, 3) for v in self.rgb], "spec": self.spec, "rough": self.rough,
            "confidence": self.confidence, "source": self.source,
            "warnings": self.warnings,
        }


# ------------------------------------------------------------------ L2 工作室档案
def load_profile(name: str | None) -> dict:
    if not name:
        return {}
    p = CONV / f"{name}.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


PREFIXES = ("ori-", "ref-", "x-", "orig-")
COPPER = ("brass", "copper", "bronze", "铜", "黄铜", "紫铜")


def _strip_prefix(n: str) -> str:
    low = n.lower()
    for p in PREFIXES:
        if low.startswith(p):
            return n[len(p):]
    return n


def _tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[-_/|::\s]+", s) if t]


def resolve(name: str, layer: str | None = None,
            profile: dict | None = None,
            overrides: dict | None = None) -> Resolution:
    """把材质名解析成光学属性。overrides 是业主确认过的 {name: rgb}。"""
    profile = profile or {}
    warns: list[str] = []
    orig = (name or "").strip()
    n = _strip_prefix(orig)
    low = n.lower()
    toks = _tokens(n)

    # --- 物理类型：先看首段（结构），再看档案补充表，再全名关键词
    phys = None
    src = "?"
    if toks:
        head = toks[0].upper()
        head = profile.get("type_alias", {}).get(head, head)
        if head in OPTICS:
            phys, src = head, "name-prefix"
        elif head in ALIAS:
            phys, src = ALIAS[head], "name-prefix(alias)"

    # 多段检测：材质名后半段常写明「brass / terrazzo」，比首段更具辨识度
    if phys is None:
        for k, v in {**profile.get("extra_types", {}), **ALIAS}.items():
            if k.lower() in low:
                phys, src = v, "keyword"
                break
    copper = any(c in low for c in COPPER)

    if phys is None:
        phys, src = "DEFAULT", "fallback"
        warns.append(f"材质「{n}」无法判定物理类型，按 DEFAULT 处理 —— 请确认")

    r, g, b, spec, rough, conf = OPTICS[phys]

    # --- 明暗修饰（启发式）
    for keys, k in MODIFIERS:
        if any(w in low for w in keys):
            r, g, b = r * k, g * k, b * k
            break

    # --- 部位
    part = "unknown"
    hay = f"{low} {(layer or '').lower()}"
    for pname, keys in PART_RULES:
        if any(k in hay for k in keys):
            part = pname
            break
    if part == "unknown":
        warns.append(f"部位未判定（材质「{n}」，图层「{layer or '—'}」）")

    # --- 铜系（启发式：金属 + 暖色偏移，比纯 METAL 的灰贴近实际）
    if copper:
        r, g, b = 0.320, 0.240, 0.160
        spec, rough = 0.30, 0.10
        if conf == "low":
            conf = "medium"
        warns.append(f"「{n}」疑似铜/黄铜，已按铜系取值；请确认是实铜还是涂层")

    # --- 物理下限（启发式：修饰词不应把深色木/石压到不物理的低值）
    floor_rgb = {"WOOD": 0.060, "STONE": 0.090, "METAL": 0.060}.get(phys, 0.030)
    r, g, b = max(r, floor_rgb), max(g, floor_rgb), max(b, floor_rgb)

    if phys == "DEFAULT" and src == "name-prefix":
        warns.append(f"「{n}」是占位材质（Default/DEFAULT 系），必须由业主确认实际材料")

    # --- 项目覆盖：最后一步，一票否决。
    # 任何启发式（修饰词 / 铜系 / floor 钳制）都不得改写业主确认值，
    # 否则报告会用着 A 的数值、却标着"业主确认"——那是诚信问题，不是精度问题。
    hit = None
    if overrides:
        for key in (orig, n):
            if key in overrides:
                hit = overrides[key]
                break
    if hit is not None:
        r, g, b = float(hit[0]), float(hit[1]), float(hit[2])
        src, conf = "owner-confirmed", "high"
        # 启发式阶段基于名字的猜测（铜系/占位）在人工确认后不再成立，撤掉
        warns = [w for w in warns if ("铜" not in w and "占位" not in w)]

    return Resolution(name=orig, physical=phys, part=part, rgb=(r, g, b),
                      spec=spec, rough=rough, confidence=conf, source=src, warnings=warns)


def resolve_all(names: list[str], profile: dict | None = None,
                overrides: dict | None = None, strict: bool = False) -> dict:
    """批量解析。

    strict=True 时，只要有材质落到 DEFAULT 且未经业主确认，就抛异常中止
    —— 这是 SKILL.md「未映射的材质必须报错中止」的可执行版本。
    （包内没有建壳脚本，所以中止必须在这里发生，不能指望调用方自觉。）
    """
    out = {}
    unmapped = []
    for n in names:
        res = resolve(n, profile=profile, overrides=overrides)
        out[n] = res.as_dict()
        # 占位材质（Default / DEFAULT-*）同样算未映射，除非业主已确认
        if res.physical == "DEFAULT" and res.source != "owner-confirmed":
            unmapped.append(n)
    if strict and unmapped:
        raise ValueError(
            "存在未确认的占位/未识别材质，已中止："
            + "、".join(unmapped)
            + "。请补进材料表（overrides）或 conventions 档案后重试。")
    return {"resolved": out, "unmapped": unmapped}
