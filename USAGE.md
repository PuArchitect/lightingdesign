# 使用说明（v2.5.0）

## 1. 包结构

```
lightingdesign/
├── SKILL.md              技能本体（冻结题 / 七阶段 / 六类图 / 46 项终审）
├── AGENTS.md             仓库级硬规则
├── README.md             门面
├── USAGE.md              本文件
├── WINDOWS.md            Windows 运行注意
├── WORKBUDDY.md          WorkBuddy 精简流程
├── scripts/
│   ├── 00_preflight_env.py       环境指纹与 Radiance 冒烟
│   ├── 00_state_manager.py       状态机 / 交接单 / 能力级校验
│   ├── 01b_room_lock_from_project.py  冻结题 → room_lock + 确认图
│   ├── 02_rad_core.py           光学换算 / 灯槽 / 材质映射
│   ├── 03_audit_closure.py      闭合审计
│   ├── 04_render_svg_a3.py      A3 1:25 定位图
│   ├── 05_build_report_pdf.py   浏览器打印（备选）
│   ├── 05b_fill_report.py       模板占位符填充（备选）
│   ├── 06_preflight_delivery.py 46 项终审
│   ├── 07_visual_qc_lint.py     视觉/版式 lint
│   ├── 08_orchestrator.py       多 Agent 驱动
│   └── tools/                   svg→pdf、Story 报告、主题生成、审计
├── agents/               5 张角色卡
├── PROMPTS/              Start + A/B/C/D 提示词 + Runbook
├── schemas/              room_lock / results JSON Schema
├── themes/               neutral_light / cigar_dark / warm_minimal / _template
├── golden/               交付校验器 + manifest 模板
└── project/              雪茄吧房间四冻结题与实测几何（示例）
```

## 2. 快速开始

```powershell
python scripts/00_preflight_env.py --project-id demo --out work/env_fingerprint.json
python scripts/01b_room_lock_from_project.py --project project/project_room4_雪茄吧.json --canonical project/整间房间数据.json --out-json work/room_lock.json --out-png work/00_房间边界确认图.png
# Stage 2/3 由 Agent B 产出 scheme_init.json / results.json / closure_audit.json
python scripts/04_render_svg_a3.py --room-lock work/room_lock.json --results work/results.json --out-svg work/L-04.svg
python scripts/tools/svg_to_a3_pdf.py --svg work/L-04.svg --out-pdf work/L-04_A3.pdf
python scripts/tools/make_theme.py --base neutral_light --accent "#0F766E" --cover-style light --out themes/my_project.json
python scripts/tools/report_story_room4.py --theme themes/my_project.json
python scripts/06_preflight_delivery.py --delivery-dir work/delivery --project project/project_room4_雪茄吧.json --lint
```

## 3. 报告主题

- 不规定配色：模板只定义 token；主题从业主 CI / 主材 / 色温 / 参考图提取；
- `neutral_light` 默认，`cigar_dark` 只用于深色奢华（雪茄/威士忌吧），`warm_minimal` 用于住宅/茶室；
- 主题只改视觉，**不改文案与结论**；
- `project.json` 的 `design_tone` 记录依据，`report_theme` 记录选择。

## 4. 终审 46 项

`06_preflight_delivery.py --lint` 检查：冻结题一致性、能力级、T-A/T-B、六类图（报告内+交付目录）、物理溯源、闭合校验、交接清单、质检预览页数、state 签核、A3 图幅/文本层、README 双轨、体积、重复段落等。

## 5. 常见问题

| 现象 | 处理 |
|---|---|
| 能力判定 L2 | 查 `env_fingerprint.json` 的 `radiance_smoke` 与 `warnings`；RAYPATH 配好再重跑 |
| 报告中文变方块 | 用 Story 路径（PyMuPDF 内嵌字体）或安装中文字体 |
| A3 中文缺失 | 用 `svg_to_a3_pdf.py`（PyMuPDF 矢量路径），不依赖浏览器 |
| 终审缺交接清单/质检预览 | 按 `01_交接清单.md`、`05_质检预览/pNN.png` 补齐 |
