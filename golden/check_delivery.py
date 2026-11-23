# -*- coding: utf-8 -*-
"""golden set 交付校验器 v1

用法：
    python check_delivery.py <交付目录> --manifest <manifest.json> --project <project.json>
    python check_delivery.py --all <manifests目录> --project <project.json> --out <结果.md>

校验项（对应技能 v1.2 的 G9/G11）：
  1. room      房间尺寸 / 面积与冻结题一致（±1%）
  2. level     能力级别不低于 required_level
  3. files     交付清单齐全（报告 / A3 / 伪彩 / 灯具表 / 材料表 / results / preflight / README / 交接清单）
  4. a3        A3 图为真实 A3 图幅（841×1191 pt，容差 6 pt）
  5. preflight preflight 报告 FAIL=0
  6. targets   报告中同时出现 T-A 与 T-B（含 40–60 / 90–150 / 300–500 / 75 lx）
  7. numbers   results.json 中能识别到面积字段，且与冻结题一致
退出码：全 PASS 为 0，否则 1。
"""
import argparse, json, os, re, sys

try:
    import pymupdf as fitz
except Exception:
    fitz = None
try:
    from docx import Document
except Exception:
    Document = None

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"

def ok(desc, status, detail=""):
    return {"item": desc, "status": status, "detail": detail}

def read_text(path):
    p = path.lower()
    if p.endswith(".pdf") and fitz:
        try:
            d = fitz.open(path)
            t = "\n".join(pg.get_text() for pg in d)
            d.close()
            return t
        except Exception as e:
            return ""
    if p.endswith(".docx") and Document:
        try:
            d = Document(path)
            parts = [p.text for p in d.paragraphs]
            for tb in d.tables:
                for row in tb.rows:
                    for c in row.cells:
                        parts.append(c.text)
            return "\n".join(parts)
        except Exception:
            return ""
    if p.endswith((".md", ".txt")):
        for enc in ("utf-8", "utf-8-sig", "gbk", "utf-16", "utf-16-le"):
            try:
                return open(path, encoding=enc).read()
            except Exception:
                continue
    return ""

def find_area(obj):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (int, float)) and "area" in k.lower() and 5 <= float(v) <= 100:
                out.append(float(v))
            elif isinstance(v, (dict, list)):
                out.extend(find_area(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(find_area(v))
    return out

def check_one(delivery_dir, manifest_path, project):
    m = json.load(open(manifest_path, encoding="utf-8"))
    res = []
    base = os.path.abspath(delivery_dir)
    files = m.get("files", {})

    # 1 room
    room = m.get("room", {})
    pw, pd = project["scope"]["size_m"]["W"], project["scope"]["size_m"]["D"]
    try:
        w = float(room["x1"]) - float(room["x0"])
        d = float(room["y1"]) - float(room["y0"])
        ew, ed = abs(w - pw) / pw, abs(d - pd) / pd
        if ew <= 0.01 and ed <= 0.01:
            res.append(ok("房间尺寸", PASS, f"{w:.3f}×{d:.3f} m（冻结题 {pw}×{pd}）"))
        else:
            res.append(ok("房间尺寸", FAIL, f"{w:.3f}×{d:.3f} m，与冻结题 {pw}×{pd} 偏差 W {ew:.1%} / D {ed:.1%}"))
    except Exception as e:
        res.append(ok("房间尺寸", FAIL, f"manifest room 字段缺失或无效：{e}"))

    # 2 level
    lvl = str(m.get("level", "")).upper()
    req = str(project["capability"]["required_level"]).upper()
    if lvl.startswith(req) or (req == "L3" and lvl.startswith("L3")):
        res.append(ok("能力级别", PASS, lvl))
    else:
        res.append(ok("能力级别", FAIL, f"{lvl or '未声明'} < 要求 {req}（L2 不得作为验收依据）"))

    # 3 files
    required = ["report", "a3", "results", "preflight", "readme", "handover", "lamp_table", "material_table"]
    missing = []
    for k in required:
        v = files.get(k)
        if not v:
            missing.append(k)
        else:
            p = v if os.path.isabs(v) else os.path.join(base, v)
            if not os.path.exists(p):
                missing.append(f"{k}({v})")
    pseudo = files.get("pseudo") or []
    if not pseudo:
        missing.append("pseudo")
    else:
        for v in pseudo:
            p = v if os.path.isabs(v) else os.path.join(base, v)
            if not os.path.exists(p):
                missing.append(f"pseudo({v})")
    if missing:
        res.append(ok("交付清单", FAIL, "缺：" + "、".join(missing)))
    else:
        res.append(ok("交付清单", PASS, "9 类齐全"))

    # 4 a3
    a3 = files.get("a3")
    if a3:
        p = a3 if os.path.isabs(a3) else os.path.join(base, a3)
        if os.path.exists(p) and p.lower().endswith(".pdf") and fitz:
            try:
                d = fitz.open(p)
                r = d[0].rect
                w, h = sorted([r.width, r.height])
                d.close()
                if abs(w - 841) <= 6 and abs(h - 1191) <= 6:
                    res.append(ok("A3 图幅", PASS, f"{w:.0f}×{h:.0f} pt"))
                else:
                    res.append(ok("A3 图幅", FAIL, f"{w:.0f}×{h:.0f} pt，不是 A3"))
            except Exception as e:
                res.append(ok("A3 图幅", FAIL, f"PDF 读取失败：{e}"))
        elif os.path.exists(p):
            res.append(ok("A3 图幅", FAIL, "非 PDF 或缺少 pymupdf"))
        else:
            res.append(ok("A3 图幅", FAIL, "A3 文件不存在"))

    # 5 preflight
    pf = files.get("preflight")
    if pf:
        p = pf if os.path.isabs(pf) else os.path.join(base, pf)
        if os.path.exists(p):
            txt = read_text(p)
            mfail = re.search(r"(?:FAIL\s*(?:[=:：]\s*)?(\d+)|(\d+)\s*项?\s*FAIL)", txt, re.I)
            n = None
            if mfail:
                n = int(next(g for g in mfail.groups() if g is not None))
            if n is None:
                res.append(ok("成品自检", WARN, "preflight 存在但未能解析 FAIL 数"))
            elif n == 0:
                res.append(ok("成品自检", PASS, "FAIL = 0"))
            else:
                res.append(ok("成品自检", FAIL, f"FAIL = {n}"))
        else:
            res.append(ok("成品自检", FAIL, "preflight 文件不存在"))

    # 6 targets
    rp = files.get("report")
    if rp:
        p = rp if os.path.isabs(rp) else os.path.join(base, rp)
        txt = read_text(p) if os.path.exists(p) else ""
        need = {
            "T-A 标签": r"(?<![A-Za-z])T-A(?![A-Za-z])",
            "T-B 标签": r"(?<![A-Za-z])T-B(?![A-Za-z])",
            "75 lx": r"75\s*lx", "40–60 lx": r"40\s*[–\-~]\s*60", "90–150 lx": r"90\s*[–\-~]\s*150",
            "300–500 lx": r"300\s*[–\-~]\s*500",
        }
        miss = [k for k, pat in need.items() if not re.search(pat, txt, re.I)]
        if miss:
            res.append(ok("目标口径（T-A + T-B）", FAIL, "报告缺：" + "、".join(miss)))
        else:
            res.append(ok("目标口径（T-A + T-B）", PASS, "两套口径均出现"))
    else:
        res.append(ok("目标口径（T-A + T-B）", FAIL, "无报告文件"))

    # 7 numbers
    rj = files.get("results")
    if rj:
        p = rj if os.path.isabs(rj) else os.path.join(base, rj)
        if os.path.exists(p):
            try:
                d = json.load(open(p, encoding="utf-8"))
                areas = find_area(d)
                if not areas:
                    res.append(ok("数值出处（面积）", WARN, "results.json 中未识别面积字段"))
                else:
                    best = min(areas, key=lambda a: abs(a - 20.35))
                    dev = abs(best - 20.35) / 20.35
                    res.append(ok("数值出处（面积）", PASS if dev <= 0.01 else FAIL,
                                  f"results.json 面积候选 {sorted(set(round(a,2) for a in areas))}，最接近 {best:.2f} m²"
                                  f"（冻结题 20.35 m²，偏差 {dev:.1%}）"))
            except Exception as e:
                res.append(ok("数值出处（面积）", FAIL, f"results.json 解析失败：{e}"))
        else:
            res.append(ok("数值出处（面积）", FAIL, "results.json 不存在"))
    else:
        res.append(ok("数值出处（面积）", FAIL, "未声明 results 文件"))

    passed = sum(1 for r in res if r["status"] == PASS)
    failed = sum(1 for r in res if r["status"] == FAIL)
    warned = sum(1 for r in res if r["status"] == WARN)
    overall = PASS if failed == 0 else FAIL
    return {"delivery": m.get("id", os.path.basename(base)), "dir": os.path.relpath(base),
            "overall": overall, "pass": passed, "fail": failed, "warn": warned, "items": res}

def to_md(results, project_path):
    lines = ["# golden set 交付校验报告 v1", "",
             f"> 冻结题：`{project_path}`　｜　校验器：`golden/check_delivery.py`　｜　生成时间：自动",
             "",
             "| 样本 | 结论 | PASS | FAIL | WARN |",
             "|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['delivery']} | {r['overall']} | {r['pass']} | {r['fail']} | {r['warn']} |")
    lines += ["", "## 逐项明细", ""]
    for r in results:
        lines.append(f"### {r['delivery']}")
        lines.append("")
        lines.append("| 校验项 | 结果 | 说明 |")
        lines.append("|---|---|---|")
        for it in r["items"]:
            lines.append(f"| {it['item']} | {it['status']} | {it['detail']} |")
        lines.append("")
    return "\n".join(lines)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("delivery", nargs="?")
    ap.add_argument("--manifest")
    ap.add_argument("--project", required=True)
    ap.add_argument("--all", help="manifests 目录：对每个 json 运行（delivery 目录取 manifest 的 delivery_dir 字段）")
    ap.add_argument("--out")
    args = ap.parse_args()

    project = json.load(open(args.project, encoding="utf-8"))
    results = []
    if args.all:
        for fn in sorted(os.listdir(args.all)):
            if not fn.endswith(".json"):
                continue
            mp = os.path.join(args.all, fn)
            m = json.load(open(mp, encoding="utf-8"))
            ddir = m.get("delivery_dir")
            if not ddir:
                print(f"skip {fn}: no delivery_dir", file=sys.stderr)
                continue
            results.append(check_one(ddir, mp, project))
    else:
        if not args.delivery or not args.manifest:
            ap.error("需要 <delivery> 与 --manifest，或用 --all")
        results.append(check_one(args.delivery, args.manifest, project))

    md = to_md(results, args.project)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(md)
        print("written", args.out)
    else:
        print(md)

    for r in results:
        print(f"{r['delivery']}: {r['overall']} (PASS {r['pass']} / FAIL {r['fail']} / WARN {r['warn']})")
    sys.exit(0 if all(r["overall"] == PASS for r in results) else 1)

if __name__ == "__main__":
    main()
