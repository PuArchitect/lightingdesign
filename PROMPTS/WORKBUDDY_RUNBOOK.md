# WorkBuddy 运行手册（v2.1）

> WorkBuddy **没有原生子 Agent**。这里的「多 Agent」= 5 个阶段 × 干净会话 + 50 行交接单。
> 你不需要写代码，只需要按顺序粘贴提示词 + 跑几条命令。

---

## 0. 一次性准备（5 分钟）

1. 把 `lightingdesign_v2.1/` 放到纯英文路径，例如 `D:\ldtest\lightingdesign_v2.1`（Radiance 不认中文路径）；
2. 确认 Python 可用：`python -c "import sys; print(sys.executable)"`（不要用 WindowsApps 假别名）；
3. 建工作目录，例如 `D:\ldtest\room4_work`；
4. 在 WorkBuddy 里**确认技能是否真的加载**：打开一个新会话，问「你是否加载了 lightingdesign v2.1 技能？技能目录在哪？」。
   - 若没加载（v1 的教训：本机 WorkBuddy 当时就没加载），**不要依赖自动技能发现**，在提示词里直接写技能路径、让它读文件。

初始化状态机：

```powershell
python "D:\ldtest\lightingdesign_v2.1\scripts\00_state_manager.py" init --workdir "D:\ldtest\room4_work" --project-id cigar_room4
```

---

## 1. 角色切换规则（最重要）

| 阶段 | 谁做 | 会话怎么开 | 允许读 | 必须停 |
|---|---|---|---|---|
| Stage 0–1 | Agent A | 新会话 | handoff + 角色卡 01 + 输入 | **Stage 1 后停**：给用户看边界确认图 |
| Stage 2–3 | Agent B | **新会话**（清空上下文） | handoff + 角色卡 02 | **Stage 2 后停**：业主确认材质/目标 |
| Stage 4–5 | Agent C | 新会话 | handoff + 角色卡 03 | 不停，交审计 |
| Stage 6–7 | Agent D | 新会话 | handoff + 角色卡 04 + 交付目录 | 审计 FAIL 打回 C |

> 进入新会话后**只粘三段**：角色提示词（`PROMPTS/0X_*.md`）+ 当前 `state/handoff_brief.md` 的内容 + 一句「按提示执行，做完 verify + checkpoint 再停」。
> **不要**把上一阶段的终端日志、试错过程粘进新会话——这正是 v1 结果不稳的原因之一。

---

## 2. 逐步操作

### Step 0 · 启动

新会话粘 `PROMPTS/00_START.md`（把 `<V>`/`<WORK>` 换成实际路径），让它先跑：

```powershell
python "D:\ldtest\lightingdesign_v2.1\scripts\08_orchestrator.py" status --workdir "D:\ldtest\room4_work"
```

预期：显示 `current: STAGE_0_ENV`，next = STAGE_0_ENV。

### Step 1 · Stage 0–1（Agent A）

粘 `PROMPTS/01_surveyor.md`。它应产出：
- `env_fingerprint.json`（能力级别 L3/L2；若 BLOCKED 停）；
- `room_lock.json` + `00_房间边界确认图.png`（房间四应为 20.35 m² / 5.48×3.70）。

**人工门禁**：让它把确认图路径、尺寸、warnings 列给你；你确认后再让它 `checkpoint STAGE_1_GEOM`。

### Step 2 · Stage 2–3（Agent B）

**新会话**，粘 `PROMPTS/02_physicist.md` + handoff。产出 `scheme_init.json` → 停在材质/目标确认（人工门禁 2）→ 继续出 `results.json` + `closure_audit.json`。

检查点：闭合校验偏差 ≤1%；results 面积 20.35；Uo 双口径齐全。

### Step 3 · Stage 4–5（Agent C）

新会话，粘 `PROMPTS/03_designer.md` + handoff。产出六类图：平面布局图（A3 SVG+PDF，420×297）、剖面示意图（横剖面 PNG）、照度图（伪彩 PNG）、大样图（节点 PNG/SVG）、灯光渲染图（真彩/效果图）、灯具表（xlsx），以及含这六类图的报告 PDF；页数不限（建议 6–12）。

### Step 4 · Stage 6–7（Agent D）

新会话，粘 `PROMPTS/04_auditor.md` + handoff。先跑 `07_visual_qc_lint.py`，再读图复核，最后组装双轨交付包并跑 `06_preflight_delivery.py --lint`。

**只有 FAIL=0（46 项，含六类图报告内+交付目录双查）才让它 checkpoint STAGE_7_DELIVERY。**

---

## 3. 常见卡点

| 现象 | 原因 | 处理 |
|---|---|---|
| Stage 0 判定 L2，但机器有 Radiance | RAYPATH 没配 / 冒烟失败 | 让它把 `env_fingerprint.json` 的 `warnings` 与冒烟值贴出来；按提示设 RAYPATH 后重跑 |
| A3 PDF 中文变方块 | 浏览器/字体问题 | 用 `svg_to_a3_pdf.py`（优先 PyMuPDF 矢量路径，不依赖浏览器字体） |
| 报告 PDF 打不开/空白 | 05 需要 Chrome/Edge | 安装浏览器，或让 WorkBuddy 用 `--headless=new` 路径；实在不行先交 docx |
| 状态机报「缺 scheme_init.json」 | Stage 2 没落盘 | 让 Agent B 先写 scheme_init 再 checkpoint |
| 它想跳阶段 | 模型自觉 | 拒绝：`08_orchestrator` 与 `00_state_manager` 都会拦；必要时 `--force` + 原因入账本 |
| 交付被 lint 打回 | 空白页/页底留白/字体未嵌入 | 让它按 `qc_lint_report.txt` 定位到页修 |

---

## 4. 你实际要做的（一句话版）

**每个阶段只做三件事**：粘提示词 → 看它跑 `verify-stage` → 人工门禁处点头。代码和门禁由脚本负责，你只做两个判断：**房间对不对、目标/材质确认不确认**。
