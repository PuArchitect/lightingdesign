# WorkBuddy 精简流程（v2.5.0）

WorkBuddy 没有原生子 Agent：用“新会话 + 交接单”分段。

1. 新会话粘 `PROMPTS/00_START.md`，把 `<V>` 换成本仓库绝对路径、`<WORK>` 换成工作目录；
2. Stage 0–1 粘 `PROMPTS/01_surveyor.md`，停在**房间边界确认图**；
3. Stage 2–3 粘 `PROMPTS/02_physicist.md`，停在**材质/目标确认**；
4. Stage 4–5 粘 `PROMPTS/03_designer.md`，产出六类图 + 报告；
5. Stage 6–7 粘 `PROMPTS/04_auditor.md`，跑 `07` lint 与 `06 --lint`，FAIL=0 才放行。

规则：

- 一次只做一个 Stage，按 `08_orchestrator.py next` 走；
- 只读 `state/handoff_brief.md` + 角色卡，不读旧日志；
- 每个 Stage 后 `verify-stage` PASS 再 `checkpoint`；
- 报告用 Story（无浏览器）或 `05b`+`05`（有浏览器），不得用 `insert_text` 直接排。
