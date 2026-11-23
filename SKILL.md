---
name: lightingdesign
version: 2.5.0
description: 室内照明设计全流程多 Agent 技能（v2.2：整间口径 + T-A/T-B 双目标 + room_lock + golden；交付标准升级为“设计版 8–12 页报告 + A3 + 真彩渲染 + 节点大样”，无浏览器 Story 出版；支持 L2/L3，状态机 + 防静默失效审计 + 视觉 lint）
---

# Lighting Design Skill v2.0

> 适用平台：DeepSeek Harness / WorkBuddy / Codex / zcode  
> 核心架构：**基于文件系统的黑板模式（Blackboard）+ 1 总控 / 4 专职角色隔离 + 固化 Python 核心库**

---

## 0. 五条工程铁律（违反任意一条视为任务失败）

1. **禁止静默降级**：必须先运行 `scripts/00_preflight_env.py` 明确能力等级（`L3` 或 `L2`）并落盘 `env_fingerprint.json`。缺工具链必须显式告知用户，严禁自行退化为自由发挥。
2. **单一数据源（SSOT）**：所有几何尺寸必须读取 `room_lock.json`（符合 `schemas/room_lock.schema.json`），所有计算与标定结果必须落盘至 `results.json`（符合 `schemas/results.schema.json`）。严禁下游脚本 `import` 上游内存变量。
3. **禁止手写物理换算与裸拼图**：必须调用 `scripts/02_rad_core.py` 进行 Radiance 亮度换算（`cd/m² = 179 × radiance`，严禁 `/π`）和 `CoveRect` 强类型校验；必须调用 `scripts/04_render_svg_a3.py` 生成 A3 1:25 定位图。
4. **中文路径隔离**：Radiance 计算工作目录强制设在纯英文路径（如 `C:\Temp\ld_<project_id>`），完成后再归档至中文目标目录。
5. **验收红线**：无 IES 配光文件（C 级数据）时，绝对照度误差标注为 `±20–30%`。**T-A 验收口径（0.75 m / 75 lx @ 酒吧间）只允许在 L3 + 明确不确定度声明下作为设计目标出现，不得写成施工验收条款**；T-B（40–60 / 90–150 / 300–500 lx）用于场景与调光，两套并列、不得混用。

---

## 0.1 v2.1 冻结题（强制）

Stage 0 起必须读取 `project/*.json`（冻结题），它是本项目的唯一题面：

- `scope`：房间范围（整间 / 座区）、完成面 bbox、设计面积、统计剔除项（如服务核）；
- `targets`：T-A（验收：0.75 m / 75 lx，维护系数 0.80）与 T-B（运行：40–60 / 90–150 / 300–500 lx）；
- `deliverables` 与 `regression`：交付清单与跨平台验收标准。

`room_lock.json` 是它的几何段，不得脱离冻结题单独定义范围。`golden/check_delivery.py` 是它的验收器。

---

## 1. 多 Agent 编排与断点续传协议

所有进度与上下文压缩由 `scripts/00_state_manager.py` 维护在 `state/` 目录下，**不依赖模型记忆**：

- `state/workflow_state.json`：阶段状态机 + 产物 MD5。开机/续跑必须先运行 `check-stale`，上游产物变更会自动将下游标为 `STALE`。
- `state/decision_log.jsonl`：只追加的防失忆账本。用户提出任何新约束/口径变更，立即调用 `add-decision` 记录。
- `state/handoff_brief.md`：每次切换角色前通过 `pack-handoff` 生成的 **≤ 50 行** 压缩交接单，严禁混入终端报错日志与作废初稿。

### 角色分配（详见 `agents/` 目录）

| 角色卡 | 负责阶段 | 核心任务 | 上下文处理 |
| :--- | :--- | :--- | :--- |
| `agents/00_orchestrator.md` | 全程调度 | 状态机维护、人工门禁把控、打包交接单 | 只读 `state/`，不看代码与终端日志 |
| `agents/01_surveyor.md` | Stage 0–1 | 环境指纹、`.3dm` 包围盒提取、房间边界锁定 | 产出 `room_lock.json` 后**立即释放** |
| `agents/02_physicist.md` | Stage 2–3 | 五层光策略、Radiance/L2 计算、材质与闭合审计 | 产出 `results.json` 后**立即销毁** |
| `agents/03_designer.md` | Stage 4–5 | A3 1:25 SVG 定位图、8–12 页精排 PDF、双轨打包 | 零工程噪音，严禁改写物理数值 |
| `agents/04_auditor.md` | Stage 6–7 | 120 dpi PNG 视觉自检（最多 3 轮）+ 终审硬门禁 | 独立裁判，严禁与 Agent C 共享上下文 |

> **弱平台/单会话兼容**：在不支持原生子 Agent 的平台（如 WorkBuddy）上，每完成一个角色后，执行 `checkpoint` 并开启干净上下文，仅挂载 `state/handoff_brief.md` 与下一角色卡续跑。

---

## 2. 七阶段门禁工作流

### Stage 0：环境指纹与能力定级（Agent A）
- 运行 `python scripts/00_preflight_env.py --project-id <id> --out env_fingerprint.json`。
- 拦截 WindowsApps 假 Python 别名，锁定 `L3` / `L2`，确认无头浏览器与中文字体状态。

### Stage 1：几何提取与房间边界锁定（Agent A）★ 人工确认门禁 1
- **优先**运行 `python scripts/01b_room_lock_from_project.py --project project/<冻结题>.json --canonical project/整间房间数据.json`：
  由冻结题 + 实测几何生成 `room_lock.json` 与真实平面确认图，不在 bbox 上猜房间。
- 仅当没有冻结题时，才用 `scripts/01_extract_geometry.py --roi ... --layers ...`（bbox 近似，须标注 confidence C）。
- 无分图层模型必须提供 **≥ 2 条交叉证据** 定位房间。
- **门禁**：输出 `room_lock.json` 与 `00_房间边界确认图.png`，**停下等人工确认**。图模不一致须记入 `discrepancies_to_confirm`。

### Stage 2：分层照明策略与 5 场景定义（Agent B）★ 人工确认门禁 2
- 按冻结题写死双口径：**T-A 验收**（0.75 m 工作面 75 lx，初始值 94 lx）与 **T-B 运行**（环境 40–60 / 桌面 90–150 / 重点 300–500 lx），分 5 场景。
- 建立五层光结构（环境基底 / 轮廓洗墙 / 工作面主力 / 重点焦点 / 氛围识别）。
- **门禁**：输出材质反射率假定等级（A/B/C/D 级）与待确认清单，**业主确认后再建壳计算**。

### Stage 3：物理计算与防静默失效审计（Agent B）
- 强制调用 `scripts/02_rad_core.py` 与 `scripts/03_audit_closure.py`：
  1. 壳体材质审计：未识别原始模型材质不得进入计算壳。
  2. 跌级/挑檐灯槽验证：探针检测遮挡或采用等效洗亮带折算（注明槽效率）。
  3. 独立闭合校验：单源之和 vs 主计算偏差 **> 1% 必须报错中止**。
- 强制双口径：Uo 分「可用区」与「活动区（距墙 ≥ 0.45 m）」；电功率与 LPD 按真实 LED 系统光效（默认 110 lm/W，C 级）折算。

### Stage 4：A3 1:25 天花定位图（Agent C）
- 运行 `python scripts/04_render_svg_a3.py`，生成精确 `420.0 × 297.0 mm`（±0.5 mm）、1:25 比例反算校验、尺寸链闭合、图例坐标写死、五项标题栏齐全的 A3 图纸；文本层必须含图名/图号/比例/图例/灯具表。
- 用 `scripts/tools/svg_to_a3_pdf.py` 转 PDF（优先 PyMuPDF，浏览器仅兜底）。

### Stage 5：设计版报告与双轨交付包组装（Agent C）
- **主路径（无浏览器）**：以 `scripts/tools/report_story_room4.py` 为模板，替换数据生成 HTML/CSS，用 PyMuPDF `Story` 逐页渲染 A4 PDF。**报告是设计作品，不是 Word 表格**：封面、色板、段落层级、图表、图注、页眉页脚缺一不可。
- **备选路径（有浏览器）**：`05b_fill_report.py` 填充 `templates/report_client.html` 的 36 个占位符 → `05_build_report_pdf.py` 无头打印；沙箱内浏览器被拒时不得降级为 `insert_text` 纯文本排版。
- **报告硬标准（页数不限，建议 6–12 页；六类图必须齐全）**：
  1. 封面：项目 / 房间 / 版本 / 日期 / 图号；
  2. 结论摘要 + 现状条件（含设计依据）；
  3. 光环境目标：T-A 验收与 T-B 运行双口径并列；
  4. **平面布局图**：A3 灯位定位图，报告内有裁图或缩略图；
  5. **照度图**：0.75 m 工作面伪彩图 + 色阶 + 网格说明；
  6. **大样图**：灯槽/关键节点 1:5 示意，含控制值与安装顺序；
  7. **灯光渲染图**：真彩渲染（主视角/灯槽）或甲方效果图（标来源）；
  8. **灯具表**：编号/名称/数量/光通/功率，与五场景、控制回路同页或相邻；
  9. 施工要点 / 验收动作 / 待确认 / 局限 / 数据溯源。
- **六类交付物（缺一即 FAIL）**：

| 类型 | 文件（`01_甲方汇报包/`） | 报告内呈现 |
|---|---|---|
| 平面布局图 | `02_L-04_..._A3.pdf` | 灯位示意裁图 + 图注 |
| 剖面示意图 | `08_剖面示意图.png` | 横剖面 + 标高/尺寸 + 光的作用 |
| 照度图 | `04_..._伪彩摘要图.png` | 伪彩图 + 色阶 + 图注 |
| 大样图 | `07_灯槽节点_A-A.png`（或 SVG） | 1:5 大样 + 控制值表 |
| 灯光渲染图 | `05_真彩渲染_主视角.png`、`06_真彩渲染_天花灯槽.png` | 效果图/真彩渲染 + 机位或来源 |
| 灯具表 | `03_灯具表与五场景调光表.xlsx` | 灯具表 + 五场景 + 回路 |
| 交接清单 | `01_甲方汇报包/01_交接清单.md` | 文件核对 + 四条口头说明 |
| 质检预览 | `02_设计师复核与审计包/05_质检预览/pNN.png` | 与报告页数一致 |
- **图表要求**：≥3 张编号图（平面、伪彩、渲染），节点大样 ≥1 张；图注编号连续；图必须有来源或机位说明。
- **文件要求**：A4、字体嵌入、页脚页码、体积 ≤15 MB、Title 元数据为正式图名、Author 留空。
- **交付清单（`01_甲方汇报包/`）**：说明书 PDF、A3 PDF、灯具表+五场景表 xlsx、伪彩 PNG、真彩渲染 PNG（主视角必需，灯槽可选）、节点大样 PNG/SVG、`00_README.md`、`01_交接清单.md`。
- `02_设计师复核与审计包/`：`env_fingerprint.json`、`room_lock.json`、`results.json`、`closure_audit.json`、`preflight_delivery.txt`、`qc_lint_report.txt`、`qc_issues.json`、材料表、脚本副本。

### Stage 6：强制视觉质检闭环（Agent D）
- **先跑确定性 lint**：`python scripts/07_visual_qc_lint.py --pdf <说明书.pdf> --a3 <A3.pdf> --png-dir <120dpi目录>`。
  检查空白页 / 近空白页 / 页底大片留白 / 文字出界 / 字体未嵌入 / 数字与单位断行 / 段落重复 / 章节与图表编号 / 图片过小或低分辨率 / 页脚页码 / 报告体积 / 图片数量 / A3 幅面与文本层。**FAIL=0 才进入读图**，WARN 逐条记录。
- 再逐张调用视觉读图能力核查 120 dpi PNG（排查大片留白、重叠越界、表格断行、大样高度不足、渲染穿墙/缺色阶、封面与内页设计语言不一致）。
- 发现缺陷写 `state/qc_issues.json` 打回给 Agent C 定向修，**上限 3 轮**。

### Stage 7：终审硬门禁与放行（Agent D）
- 运行 `python scripts/06_preflight_delivery.py --delivery-dir <交付根目录> --project project/<冻结题>.json [--manifest golden/manifests/<样本>.json] --lint`。
- 终审必须同时校验：房间面积/尺寸与冻结题一致性、能力级别、T-A/T-B 双口径、**六类交付物（平面布局图/剖面示意图/照度图/大样图/灯光渲染图/灯具表）齐全**、报告设计完整性（设计依据、待确认、局限、图表）、体积 ≤15 MB、A3 图幅与文本层（图名/图号/比例/图例/灯具表）、Schema。页数不设硬门槛。
- **仅当 `FAIL = 0`（46 项）时**，执行 `checkpoint --stage STAGE_7_DELIVERY --status PASSED` 宣布交付完成。

### Stage 8（v2.1）：跨平台回归（Agent D）
- 同一冻结题在两个平台各跑一次，分别填 `golden/deliverable_manifest.template.json` 并跑 `golden/check_delivery.py`。
- 验收：房间尺寸/面积差 ≤1%；同目标下平均照度与总光通差 ≤10%；交付清单 100%；preflight 0 FAIL。


## 0.2 报告主题（开放，不规定配色）

报告模板只定义**结构与 token**，不绑定任何色系。主题来自项目本身：

1. 优先业主 CI / 品牌色；
2. 其次项目调性：主材（木/铜/石/皮）、色温（2700K 暖 / 4000K 中性）、参考效果图主色；
3. 都没有，用 `neutral_light`。

工具：

- `themes/_template.json`：完整 token 模板，复制改值即可；
- `scripts/tools/make_theme.py`：按 `--base / --accent / --cover-style / --font` 生成主题，自动推导表头、边线、提示块、封面色；
- 三个预设（`neutral_light` / `cigar_dark` / `warm_minimal`）只是**起点**，不是限制；
- 封面支持 `light` / `dark` 两种调性；字体可换（正文/标题）。

**主题只改视觉，不改文案与结论；报告正文必须按项目重写。棕金只是雪茄吧的选择。**

`project.json` 用 `design_tone`（关键词/色温/主材/品牌色/封面调性）记录依据，用 `report_theme` 记录最终选择。

## 0.2.1 成功样本

成功样本：WorkBuddy 用 v2.2.3 完成 11 页 / 六类图 / 46 项 FAIL=0；具体 manifest 由项目本地生成，不随仓库分发。


## 0.3 多 Agent 降级路径（实测）

S5 由 WorkBuddy 在同一会话按 Stage 0–7 分段执行，`decision_log.jsonl` 记录 physicist/designer/auditor 三次角色切换；`checkpoint` 现在每次重写 `state/handoff_brief.md`，避免交接单停留在初始状态。
