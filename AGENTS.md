# AGENTS.md — 照明设计工作约定（v2.5.0）

本仓库是 `lightingdesign` 技能。详细流程见 `SKILL.md`；面向人的说明见 `USAGE.md`。
技能版本：**v2.5.0**（见 `SKILL.md` frontmatter，单一事实来源）。

## 开工四步

1. **环境指纹**：`python scripts/00_preflight_env.py --project-id <id> --out <work>/env_fingerprint.json`
   —— 能力级别以它为准（L3/L2/L1），**不允许手填或默认 L3**。
2. **读冻结题**：`project/<项目>.json`（范围、面积、T-A/T-B、交付与回归要求）。
3. **看状态机**：`python scripts/08_orchestrator.py status --workdir <work>`，按 `next` 执行当前阶段。
4. **声明级别**后再干活；每阶段 `start → 产物 → verify → checkpoint`，不许跳阶段。

## 五条铁律

1. 每个照度/功率数字必须能追到 `.json`，禁止手抄、估值。
2. 不确定必须标注（缺 IES、缺标高、材质待定），不许补默认值蒙混。
3. 几何 / 配光 / 材质三项各给可信度等级（A/B/C）。
4. 未识别材质必须报错或报警，禁止跳过。
5. 交付前必须 `06_preflight_delivery.py --lint` 且 **FAIL = 0**。

## 人工门禁（必须停）

- Stage 1：房间边界确认图 + `room_lock.json` → 用户确认“整间/座区、尺寸、面积”。
- Stage 2：`scheme_init.json` 的 T-A/T-B、五层策略、材质待确认清单 → 业主确认。

## 六类交付物（缺一 FAIL）

平面布局图（A3）、剖面示意图（含光束锥）、照度图（伪彩）、大样图（节点 1:5）、灯光渲染图（真彩/效果图）、灯具表（xlsx）。

另交：`00_README.md`、`01_交接清单.md`、`02.../05_质检预览/pNN.png`、`state/` 签核。

## 禁止

- 改 `project/` 冻结题、改 `results.json` 物理数值、把未通过写成 PASS
- 跳阶段、换主题改结论、把棕金当默认主题
- 用 `insert_text` 直接排报告（报告用 Story/HTML 模板）

## 每轮结束

1. `06_preflight_delivery.py --delivery-dir <pkg> --project <project> --lint`，贴结果行；
2. 报告交付包路径、文件数、六类图是否齐全；
3. 新增反模式写回 `SKILL.md`。
