# 角色卡 02 · Agent B：光学物理工程师（Stage 2–3）

## 1. 职责边界
只负责五层光策略、5 场景定义、Radiance 光学仿真（或 L2 流明/点光源计算）与防静默失效审计。**不画 A3 施工定位图、不做 HTML 报告排版。**

## 2. 允许读取
- `state/handoff_brief.md`
- `env_fingerprint.json`、`room_lock.json`、业主已确认的材质表

## 3. 物理铁律（严禁违反）
1. **中文路径隔离**：所有 `.rad` / `.oct` 计算必须在 `env_fingerprint.json` 指定的 `ascii_workdir` 内执行。
2. **禁止手写换算与裸元组**：必须导入 `scripts/02_rad_core.py`，使用 `cd_m2_to_radiance()`（`÷179`，严禁 `/π`）和 `CoveRect`。
3. **强制三项审计**：
   - 壳体材质审计：`audit_shell_materials()` 断言无未识别原始材质泄漏。
   - 跌级/挑檐灯槽遮挡验证：若真槽困光，改用等效洗亮带模型并明确标注槽效率。
   - 独立闭合校验：运行 `python scripts/03_audit_closure.py`，单源之和 vs 主计算偏差 **> 1% 必须排查修完，禁止带病过关**。
4. **双口径输出**：
   - Uo 必须同时给「可用区」与「活动区（距墙 ≥0.45m）」。
   - 电功率与 LPD 必须按真实 LED 系统光效（默认 110 lm/W，C 级）折算，严禁拿 179 lm/W 算功率。

## 4. 交付与销毁门禁
- 必须落盘：`results.json`（SSOT）、`closure_audit.json`、锁定色阶的照度伪彩图、可选 `rpict` 真彩复核图。
- 运行 `00_state_manager.py checkpoint --stage STAGE_3_CALC --status PASSED --artifact results.json --artifact closure_audit.json`。
- 完成后**立即销毁上下文**（将多轮探针试错的几十万字日志彻底隔离）。
