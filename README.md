# AI for Classic Architects · lightingdesign draft quality

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

Clone this repository into the working directory of your agent, then run the bootstrap once:

把这个仓库克隆到你 Agent 的工作目录，然后跑一次自举：

```bash
git clone https://github.com/PuArchitect/lightingdesign.git
cd lightingdesign
python scripts/bootstrap.py                # 只体检：缺什么、现在什么级别
python scripts/bootstrap.py --install --yes   # 补齐（需网络；无需管理员权限）
```

`bootstrap.py` writes two files:

- `bootstrap_report.md` — what was installed, what is still missing, how to set `RAYPATH`
- `capabilities.json` — the resulting level: `L3` / `L2` / `L1`

### Platform notes / 各平台

| Platform | How | Suggested level |
|---|---|---|
| DeepSeek Harness | point the workspace at this repo, or copy `SKILL.md` into your skills directory | L3 |
| ChatGPT work / codex | repo root as working dir; `AGENTS.md` is picked up automatically | L3 |
| zcode | same; keep single commands under 60 s, write results to disk | L2–L3 |
| workbuddy | same; designed conservatively for L2 — one stage per step, file-based checkpoints | L2 |

### Where to read next / 接下来读什么

- `SKILL.md` — the workflow itself: five hard rules, seven gated stages, the downgrade ladder, and seven anti-patterns that all really happened.
- `AGENTS.md` — repository-level rules (auto-read by codex / zcode / workbuddy).
- `USAGE.md` — the longer human-facing guide.
- `templates/` — handover checklist, material-table template, report skeleton.

## License / 许可

Internal team use. Ask before redistributing outside the studio.
