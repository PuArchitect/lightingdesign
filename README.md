# AI for Interior Lighting Designers · lightingdesign

For designers who turn spatial intent into light — private rooms, bars, restaurants, and the tiny teams working beside them. This skill is shared as a practical companion for turning "it looks right" into numbers someone else can check: materials, fixtures, illuminance, and a report that says honestly what it does not know. Cheers.

就献给坚持把空间想法照亮的室内设计师伙伴们，也就给与你们并肩工作的超小型团队。希望这份技能能帮大家把光的意图推演成可以复核的数——材料、灯具、照度，以及一份敢说自己不知道什么的报告。Cheers。

## What it does / 能做什么

`lightingdesign` guides interior lighting work from handover to a reviewable report. For a space it follows:

Evidence and materials → geometry → fixture positions → calculation → plan sheets → report → self-check.

证据与材料 → 几何 → 灯位 → 计算 → 图版 → 报告 → 自检。

It does not assume your machine already has Radiance. The first run scans the environment and installs what is missing — `pyradiance` ships the compiled binaries, so no admin rights and no separate installer are needed.

它不假设你的电脑已经装好 Radiance。第一次运行会扫描环境并补齐缺失组件——`pyradiance` 自带编译好的二进制，不需要管理员权限，也不用跑安装程序。

It also works when the environment is incomplete: capability is downgraded (L3 → L2 → L1), but the reporting standard is not. If it cannot calculate, it says so on the cover page instead of inventing numbers.

环境不齐时它照样能用：能力可以降级（L3 → L2 → L1），但报告标准不降。不能算就写在封面上，而不是编一个数。

## Invoke / 调用

Use `lightingdesign` (or `lighting`) in a request where this skill is installed. They are skill-level recognition conventions, not product-registered commands. Asking for discussion or a prompt alone does not authorize calculation or file changes.

可以说"lightingdesign，先整理这份模型和图纸，出一版材料表给我确认"，也可以说"lighting，按上次的配比重算这一间，只要数据不要报告"。有明确的计算或出图授权、且没有关键未决项时，助手可直接推进。

## Install / 安装

Clone this repository into the working directory of your agent, then run the environment probe once:

把这个仓库克隆到你 Agent 的工作目录，然后跑一次环境指纹：

```bash
git clone https://github.com/PuArchitect/lightingdesign.git
cd lightingdesign
python scripts/00_preflight_env.py --project-id demo --out env_fingerprint.json
```

> **Windows 用户先看 [`WINDOWS.md`](WINDOWS.md)** —— 用哪个窗口输入，以及为什么你的 `python` 可能是 Microsoft Store 的假命令。
> **Windows users:** read [`WINDOWS.md`](WINDOWS.md) first for the same reason.

`00_preflight_env.py` writes `env_fingerprint.json`:

- capability level: `L3` / `L2` / `L1`
- `radiance_smoke` — real rtrace smoke test (2.176 W/m² ±5%)
- `ascii_workdir` / `warnings`

### Platform notes / 各平台

| Platform | How | Suggested level |
|---|---|---|
| DeepSeek Harness | point the workspace at this repo, or copy `SKILL.md` into your skills directory | L3 |
| ChatGPT work / codex | repo root as working dir; `AGENTS.md` is picked up automatically | L3 |
| zcode | same; keep single commands under 60 s, write results to disk | L2–L3 |
| workbuddy | same; **read `WORKBUDDY.md` first** — a four-step condensed version for small-context agents | L2 |

**Tested / 已验证**

| Platform | Status |
|---|---|
| DeepSeek Harness | ✅ full run (L3), report + sheets + self-check, 31 items 0 FAIL |
| workbuddy | ✅ full run (L2 path), 2026-11-21 — `WORKBUDDY.md` was written from that run |
| zcode / codex | ⏳ not yet exercised end-to-end |

### Where to read next / 接下来读什么

- `SKILL.md` — the workflow itself: five hard rules, seven gated stages, the downgrade ladder, and seven anti-patterns that all really happened.
- `AGENTS.md` — repository-level rules (auto-read by codex / zcode / workbuddy).
- `WORKBUDDY.md` — condensed four-step version for small-context platforms. **Don't read `SKILL.md` in full on those.**
- `USAGE.md` — the longer human-facing guide.
- `templates/` — handover checklist, material-table template, report skeleton.

## License / 许可

Internal team use. Ask before redistributing outside the studio.


## v2.5.0 / 2026-11

本版把“交付”写成硬标准：

- **六类图**：平面布局图、剖面示意图、照度图、大样图、灯光渲染图、灯具表，缺一终审 FAIL。
- **46 项终审**：`scripts/06_preflight_delivery.py --lint`，含物理溯源、闭合校验、交接清单、质检预览、state 签核。
- **报告主题开放**：`themes/` 只定义 token；用 `scripts/tools/make_theme.py` 按业主 CI / 主材 / 色温生成任意配色与封面调性，不规定棕金。
- **两条报告路径**：Story（HTML/CSS → PDF，无浏览器）为主；`05b_fill_report.py` + `05_build_report_pdf.py` 为有浏览器备选。
- **物理真算**：`02_rad_core.py` 被 `calc_room4.py` 直接调用，产出 shell/lights rad、fine_grid 与闭合审计。

快速开始：

```powershell
python scripts/00_preflight_env.py --project-id my_project --out work/env_fingerprint.json
python scripts/01b_room_lock_from_project.py --project project/project_room4_雪茄吧.json --canonical project/整间房间数据.json --out-json work/room_lock.json --out-png work/00_房间边界确认图.png
python scripts/04_render_svg_a3.py --room-lock work/room_lock.json --results work/results.json --out-svg work/L-04.svg
python scripts/tools/svg_to_a3_pdf.py --svg work/L-04.svg --out-pdf work/L-04_A3.pdf
python scripts/tools/make_theme.py --base neutral_light --accent "#0F766E" --cover-style light --out themes/my_project.json
python scripts/tools/report_story_room4.py --theme themes/my_project.json
python scripts/06_preflight_delivery.py --delivery-dir work/delivery --project project/project_room4_雪茄吧.json --lint
```
