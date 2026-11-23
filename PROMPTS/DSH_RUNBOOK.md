# DSH / 多 Agent 平台运行手册（v2.1）

> 适用：DeepSeek Harness、Codex、zcode 等支持子 Agent 的平台。
> 特点：主控（lead）持有状态机；每个 Stage 拉起一个干净的子 Agent（只给交接单 + 角色卡），完成后立即销毁。

---

## 1. 主控循环

```powershell
python "<V>\scripts\08_orchestrator.py" status --workdir "<WORK>"
python "<V>\scripts\08_orchestrator.py" next   --workdir "<WORK>"
```

对 next 给出的阶段：

1. `start-stage` 标记 IN_PROGRESS；
2. 派发子 Agent（只含：角色卡 + `state/handoff_brief.md` + 本阶段输入路径）；
3. 子 Agent 在同一 workdir 下产出文件；
4. 主控跑 `verify-stage`（PASS 才允许 `checkpoint`）；
5. `checkpoint` 后 `pack --target-stage <下一阶段>` 生成 ≤50 行交接单；
6. 人工门禁（Stage 1 / 2）停下等用户签字。

---

## 2. 子 Agent 的任务边界（写进派发提示词）

- 只读交接单 + 角色卡 + 本阶段输入；不读其他阶段日志；
- 只写本阶段产物；不改 `results.json` 的物理数值（Agent C/D）；
- 完成即返回「产物路径 + verify 结果 + 5 行结论」，由主控登记；
- 不自行 checkpoint（由主控统一做，防止子 Agent 自签）。

---

## 3. 与 WorkBuddy 的关系

同一套文件、同一套门禁、同一套提示词（`PROMPTS/00–04`）；
区别只在「角色切换」：DSH 用子 Agent 自动隔离上下文，WorkBuddy 用**新会话 + 交接单**手动隔离。
两条路径的验收完全一致：`08_orchestrator verify-stage` + `06_preflight_delivery --lint`。

---

## 4. 实测状态（2026-11-23）

已在 DSH 上验证：状态机门禁（跳阶段/缺产物被拒）、`08` 的 status/next/start/verify 协议、交接单生成、MD5 失效传播。
**尚未验证**：真实 4 个子 Agent 的完整跑通（需要一次真实 Stage 0–7 执行）；预计在下一步与 WorkBuddy 并行验证。
