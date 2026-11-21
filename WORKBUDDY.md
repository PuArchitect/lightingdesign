# WORKBUDDY 快速指令（弱平台专用）

> 本文件是给 workbuddy 这类上下文小、命令易超时的平台准备的**精简版**。
> 完整规则见 `SKILL.md`，但**在弱平台上不要通读它**——只按下面四步做。
>
> **状态：本机（Windows / workbuddy）实测跑通，2026-11-21。**
> 那轮测试得出的结论已写进本文件（四步、三条报警、分批装包）。

---

## 第零步：想验证降级路径，不用真的卸包

```bash
# Windows PowerShell
$env:LIGHTINGDESIGN_FORCE_LEVEL='L2'; python scripts/bootstrap.py
# macOS / Linux
LIGHTINGDESIGN_FORCE_LEVEL=L2 python scripts/bootstrap.py
```

可选 `L1` / `L2` / `L3`。用来确认"没 Radiance 时会怎样"，以及报告封面是否真的标了 `_L2`。
**这只是测试开关，不是让你把 L3 的机器谎报成 L2。**

---

## 第一步：先自举，别先说话

```bash
python scripts/bootstrap.py
```

然后读 `capabilities.json`，**在回复第一句就声明级别**：

> 当前环境能力：**L2**（无 Radiance），依据 `capabilities.json`。

级别判断（不要自己猜）：

| 条件 | 级别 |
|---|---|
| Radiance + numpy + PIL + openpyxl 都有 | L3 |
| 有 PIL + openpyxl，无 Radiance 或无 numpy | L2 |
| 上面都不满足 / 不能跑 Python | L1 |

**如果连 python 都跑不了 → 直接 L1，不要试图"心算"任何照度。**

---

## 第二步：一次只做一个阶段，做完写文件

| 阶段 | 要写的文件 | 写完就停 |
|---|---|---|
| ① 交接 | `01_交接清单.md` | ✅ 停，等确认 |
| ② 材料表 | `材料表_待确认.xlsx` 或 `.md` + `manifest.json` | ✅ 停，等确认 |
| ③ 几何 | `<room>_shell.rad` 或 `.md` 说明 | 继续 |
| ④ 灯位 | `lights.rad` 或灯位表 | 继续 |
| ⑤ 计算 | `<room>_results.json` | 继续 |
| ⑥ 出图 | `<room>_伪彩.png`（无 PIL 则跳过并说明） | 继续 |
| ⑦ 报告 | `报告.docx` / `.md` | 跑自检 |

**没写出文件 = 这一步没完成。** 不要用"我已经想好了"代替文件。

---

## 第三步：三个必须停下来报警的地方

1. **缺 IES** → 写"配光 C 级，未做眩光，绝对值 ±20–30%"，**不许**拿余弦分布冒充。
2. **材质名不认识** → 报错或列表要求确认，**绝对不许跳过**（跳过天花 = 少算最重要的受光面）。
3. **缺天花标高/灯槽做法** → 写"缺，影响 10%+"，不许按层高硬算。

这三条是诚信条款，违反比算错更严重。

---

## 第四步：交付前自检

```bash
python scripts/preflight.py --artifacts <产物目录> --expected-rooms <房间数>
```

- `0 FAIL` 才能交付；`WARN` 要在回复里说明
- 跑不了就手工核四条：无 `**` 残留、无空白页、图版色阶一致、每个数字都有出处

---

## 弱平台三条硬纪律

1. **单条命令 ≤ 60 s**；装包用 `python scripts/bootstrap.py --install --yes --pkgs pillow,openpyxl` 分批
2. **每完成一步就写文件**，中断后靠文件恢复，不靠记忆
3. **不要一次读完 SKILL.md**，只读当前阶段那一节

---

## 一句话

> 能算就算，不能算就写"没算"，标 `_L2` / `_L1`。
> **一份诚实的残报告，胜过一个漂亮的假数字。**
