# Changelog

## v2.5.0 — 2026-11-23

- 交付标准：六类图（平面布局 / 剖面示意 / 照度 / 大样 / 灯光渲染 / 灯具表），缺一终审 FAIL。
- 终审：`06_preflight_delivery.py` **46 项**（含物理溯源、闭合校验、交接清单、质检预览、state 签核）。
- 报告：Story（HTML/CSS → PDF）主路径；`05b_fill_report.py` 模板填充备选；主题开放（`themes/` + `make_theme.py`）。
- 物理：`calc_room4.py` 直接 import `02_rad_core.py`，有 shell/lights rad、fine_grid、闭合 0.0% 的真算样本。
- 多 Agent：同会话分段 + 交接单实测；`checkpoint` 自动重写 `handoff_brief.md`。
- 修复：确认图墙线、面积自证、canonical 冲突、门窗/图例、能力级交叉校验等 H1/M1–M6/L1–L8。

## v1.x

历史版本见 git log。
