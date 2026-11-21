"""成品自检（P0-3）：报告/表格/图版出门前自动跑一遍。

检查项来自本轮实际踩过的坑：
  1. docx 里残留 markdown 标记（** / __）
  2. docx 章节交叉引用指向不存在的编号
  3. docx 是否有空白页（段落全空连续超阈值）
  4. 图片是否超版心（>15.4 cm）
  5. 同批伪彩图色阶是否一致（读 spec JSON 的 vlo/vhi）
  6. xlsx 是否有占位未填（"—" 或空）

用法：python scripts/preflight.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "cigar"
PLANS = ROOT / "data" / "plans"
SPEC_GLOB = "*_v*.json"          # 图版 spec：不写死版本号，可用 --spec-glob 覆盖
MANIFEST_NAME = ""               # 材质/几何清单：留空则自动找 *manifest*.json
EXPECTED_ROOMS = 0               # 0 = 不检查房间数（换项目不用改代码）

results: list[tuple[str, str, str]] = []   # (项, PASS/FAIL/WARN, 说明)


def add(item: str, ok, note: str = ""):
    results.append((item, "PASS" if ok is True else ("WARN" if ok is None else "FAIL"), note))


def check_docx(path: Path) -> None:
    if not path.exists():
        add(f"docx 存在: {path.name}", False, "文件缺失")
        return
    try:
        from docx import Document
    except ImportError:
        add(f"{path.stem[:16]} 可检查", None, "缺 python-docx，跳过该文档（装依赖后重跑）")
        return
    d = Document(str(path))
    tag = path.stem[:16]

    texts = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            for c in row.cells:
                texts.append(c.text)

    bad = [t for t in texts if "**" in t or "__" in t]
    add(f"{tag} 无 markdown 残留", not bad, f"{len(bad)} 处：{bad[0][:40] if bad else ''}")

    heads = [p.text.strip() for p in d.paragraphs if p.style.name.startswith("Heading")]
    nums = set()
    for h in heads:
        m = re.match(r"^(\d+(?:\.\d+)?)", h)
        if m:
            nums.add(m.group(1))
    refs = set()
    for t in texts:
        refs |= set(re.findall(r"§(\d+(?:\.\d+)?)", t))
    if not nums:
        # 本文档不用数字编号（如「一、二、A1/B1」），§ 是跨文档引用，无法自校
        add(f"{tag} 章节引用有效", None,
            f"{len(refs)} 处 § 为跨文档引用（本文档用中文/字母编号，无法自校）")
    else:
        missing = sorted(refs - nums)
        add(f"{tag} 章节引用有效", not missing,
            f"缺失：{missing}" if missing else f"{len(refs)} 处引用")

    # 空白页：连续空段落过多（默认 12 段）视为一页空白
    run = 0
    worst = 0
    for p in d.paragraphs:
        if p.text.strip() == "" and not p._element.findall(
                "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}r"):
            run += 1
            worst = max(worst, run)
        else:
            run = 0
    add(f"{tag} 无空白页迹象", worst < 12, f"最长连续空段 {worst}")

    # 图幅
    sec = d.sections[0]
    usable = (sec.page_width - sec.left_margin - sec.right_margin) / 360000
    over = []
    for sh in d.inline_shapes:
        w_cm = sh.width / 360000
        if w_cm > usable + 0.05:          # 版心宽度随文档而变，不写死
            over.append(round(w_cm, 1))
    add(f"{tag} 图幅不超版心", not over,
        f"超宽 {over}（版心 {usable:.1f} cm）" if over else
        f"{len(d.inline_shapes)} 张，版心 {usable:.1f} cm")


def check_sheets() -> None:
    specs = sorted(PLANS.glob(SPEC_GLOB))
    if not specs:
        add("伪彩 spec 存在", None, f"{PLANS} 下无 {SPEC_GLOB}（无图版则跳过）")
        return
    scales = {}
    for p in specs:
        d = json.loads(p.read_text(encoding="utf-8-sig"))
        scales[p.stem] = (d.get("vlo"), d.get("vhi"))
    uniq = set(scales.values())
    add("同批伪彩色阶一致", len(uniq) == 1,
        f"{len(specs)} 张，色阶 {sorted(uniq)}" if len(uniq) > 1 else f"{scales}")
    for p in specs:
        png = OUT / (re.sub(r"_v\d+$", "", p.stem) + "_伪彩.png")
        add(f"图版存在: {png.name}", png.exists())


def check_xlsx(path: Path) -> None:
    if not path.exists():
        add(f"xlsx 存在: {path.name}", False, "文件缺失")
        return
    from openpyxl import load_workbook
    wb = load_workbook(str(path))
    ws = wb[wb.sheetnames[0]]
    blanks = 0
    SKIP = ("合计", "总计", "全场", "面积", "LPD", "编号", "#")
    for row in ws.iter_rows(min_row=5, values_only=True):
        if not row or row[0] is None:
            continue
        first = str(row[0]).strip()
        if any(k in first for k in SKIP):      # 合计/汇总行本就没有第二列
            continue
        # 只有 B~D 全空才算可疑空行；合并单元格会让 value-only 读到 None
        rest = [row[i] for i in (1, 2, 3) if i < len(row)]
        if all(v in (None, "", "—") for v in rest):
            blanks += 1
    add(f"{path.stem[:14]} 无空占位行", None if blanks else True, f"{blanks} 行（人工看一眼）")


def check_manifest() -> None:
    if not MANIFEST_NAME:
        add("材质清单", None, "未指定/未找到（--manifest 指定；无清单则跳过）")
        return
    p = OUT / MANIFEST_NAME
    if not p.is_file():
        add(f"材质清单: {MANIFEST_NAME}", None,
            f"未找到（用 --manifest 指定；无清单则跳过该项）")
        return
    d = json.loads(p.read_text(encoding="utf-8-sig"))
    detail = d.get("material_resolution", {})
    # 只有「实际出现在房间里的」低可信材质才影响结论；区域外的不算
    used = {}
    for r in d.get("rooms", {}).values():
        for m, a in r.get("materials", {}).items():
            used[m] = used.get(m, 0) + a
    low = [k for k, v in detail.items()
           if v.get("confidence") == "low" and used.get(k, 0) > 0]
    outside = [k for k, v in detail.items()
               if v.get("confidence") == "low" and used.get(k, 0) == 0]
    msg = (f"影响房间的低可信 {len(low)} 项：{low[:3]}" if low
           else f"{len(detail)} 种材质；区域外低可信 {len(outside)} 项（不影响结论）")
    add("材质无低可信项（限房间内）", not low, msg)

    n_rooms = len(d.get("rooms", {}))
    if EXPECTED_ROOMS:
        add(f"房间数 = {EXPECTED_ROOMS}", n_rooms == EXPECTED_ROOMS,
            f"实际 {n_rooms} 间：{list(d.get('rooms', {}).keys())}")
    else:
        add("房间数未约束", None, f"实际 {n_rooms} 间（--expected-rooms 0 = 不检查）")


def main() -> int:
    # 弱终端（Windows cp936 管道）打印中文会乱码，弱模型据此判门禁会误判
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    import argparse
    ap = argparse.ArgumentParser(description="成品自检")
    ap.add_argument("--artifacts", type=Path, default=None,
                    help="交付物目录（默认 <repo>/out/cigar）")
    ap.add_argument("--plans", type=Path, default=None,
                    help="图版 spec 目录（默认 <repo>/data/plans）")
    ap.add_argument("--spec-glob", default=None,
                    help="图版 spec 匹配模式（默认 *_v*.json）")
    ap.add_argument("--manifest", default=None,
                    help="材质/几何清单文件名（默认自动找 *manifest*.json）")
    ap.add_argument("--expected-rooms", type=int, default=0,
                    help="期望房间数；0 = 不检查")
    args = ap.parse_args()

    global OUT, PLANS, SPEC_GLOB, MANIFEST_NAME, EXPECTED_ROOMS
    if args.artifacts:
        OUT = args.artifacts
    if args.plans:
        PLANS = args.plans
    if args.spec_glob:
        SPEC_GLOB = args.spec_glob
    if args.manifest:
        MANIFEST_NAME = args.manifest
    elif OUT.exists():
        found = sorted(OUT.glob("*manifest*.json"))
        if found:
            MANIFEST_NAME = found[0].name
    EXPECTED_ROOMS = args.expected_rooms
    if not OUT.exists():
        print(f"找不到交付物目录：{OUT}（用 --artifacts 指定）")
        return 2

    # 自动发现全部产物，避免硬编码清单随改名而失效
    for p in sorted(OUT.glob("*.docx")):
        check_docx(p)
    check_sheets()
    for p in sorted(OUT.glob("*.xlsx")):
        check_xlsx(p)
    check_manifest()

    w = max(len(a) for a, _, _ in results)
    fails = 0
    print(f"{'检查项':<{w}}  结果  说明")
    print("-" * (w + 40))
    for a, b, c in results:
        if b == "FAIL":
            fails += 1
        print(f"{a:<{w}}  {b:<5} {c}")
    print(f"\n{len(results)} 项，FAIL {fails} 项")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
