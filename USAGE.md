# 使用说明（详细）

> 门面见 `README.md`；技能本体见 `SKILL.md`；仓库规则见 `AGENTS.md`。
> 本文件是给人看的长期参考：四个平台怎么配、workbuddy 专项、质量怎么保证、怎么迭代。

---

## 1. 包里有什么

```
lightingdesign/
├── README.md               门面（安装 / 调用 / 能做什么）
├── SKILL.md                技能本体（铁律 / 七阶段门禁 / 降级阶梯 / 反模式）
├── AGENTS.md               仓库级硬规则（codex / zcode / workbuddy 自动读）
├── USAGE.md                本文件
├── scripts/
│   ├── bootstrap.py        环境自举：扫描 → 补齐 → 复验（支持离线 wheels）
│   ├── capability_probe.py 轻量探针（只报不装）
│   ├── naming_resolver.py  通用材质/图层命名解析
│   ├── preflight.py        成品自检（可 --artifacts 指向任意项目）
│   └── tyarch.json         某工作室的命名档案示例（换工作室只改这个）
├── templates/
│   ├── 01_交接清单.md
│   ├── 02_材料表模板.md
│   └── 03_报告骨架.md
└── wheels/                 离线安装包存放处（.whl）
```

---

## 2. 首次使用：先自举，再干活

```bash
python scripts/bootstrap.py                       # 体检，不动系统
python scripts/bootstrap.py --install --yes       # 补齐
python scripts/bootstrap.py --install --offline --yes   # 用 wheels/ 离线补齐
```

它做三件事：**扫描 → 补齐 → 复验**，产出 `bootstrap_report.md` 与 `capabilities.json`。

### 为什么不需要装 Radiance 应用

`pyradiance` 的 wheel **自带 Windows 预编译的 `oconv / rtrace / rpict / evalglare`**，
`pip install pyradiance` 后二进制在 `site-packages/pyradiance/bin`。
**不需要管理员权限、不需要跑安装程序、不需要配 PATH。**

**但必须配 `RAYPATH`**（bin + lib），否则 `rtrace` 找不到 `rayinit.cal`，
会对每条光线返回 `1,1,1` —— **给出看起来合理、实际全错的数**。`bootstrap.py` 会打印该导出的值。

### 补不齐就降级

| 缺什么 | 处理 |
|---|---|
| pillow / openpyxl / numpy | 必装；装不上只能 L1 |
| pyradiance | 降 L2，封面标 `_L2`，只做直射估算 |
| python-docx | 用 md 交付，标 `_L2` |
| 无网络 | `wheels/` 离线装 |
| 没有 Python | 停，或 L1 手工填模板 |

**绝不允许环境不齐却按 L3 的口径出报告。**

---

## 3. 四个平台的接入

| 平台 | 怎么接 | 建议级别 |
|---|---|---|
| **DeepSeek Harness** | 工作目录指向本仓库，或把 `SKILL.md` 放进 skills 目录 | L3 |
| **ChatGPT work / codex** | 仓库根作为工作目录，`AGENTS.md` 自动生效 | L3（先自举） |
| **zcode** | 同上；长任务拆批，每批产物落盘 | L2–L3 |
| **workbuddy** | 同上；**默认按 L2 设计** | L2 |

四个平台都能读 `AGENTS.md`，这是最稳的公共入口。

---

## 4. workbuddy 专项

workbuddy 更容易掉质量，原因通常不是模型弱，而是**长流程**：
上下文被日志挤占、命令超时、包缺失、中途忘了前面确认过的事实。

技能里已内置对策，使用时不需额外配置：

1. **阶段化落盘**：每阶段必须写出一个文件，用"文件存在"代替"我觉得做完了"
2. **单步可恢复**：中断后从文件继续，不依赖上下文记忆
3. **零依赖优先**：自检用标准库；出图用 PIL；表格用 openpyxl
4. **长命令拆批**：单条 < 60 s，结果落盘
5. **默认 L2**：不假设有 Radiance

**如果连 Python 都跑不了** → 只做 L1：用 `templates/` 手工填，封面标 `_L1`。
**这比硬着头皮编数字好一万倍。**

---

## 5. 质量不会掉的关键设计

这个包不靠"模型够聪明"来保证质量，靠三件事：

| 机制 | 作用 |
|---|---|
| **门禁** | 每阶段结束必须产出文件并停下等人确认，不允许一口气跑完 |
| **降级阶梯** | 能力不足时**降低计算等级**，而不是降低报告标准 |
| **自检** | `preflight.py` 不需要懂业务，也能查出排版/引用/色阶问题 |

一句话：**能力可以降，标准不能降；不能算就写"没算"，不许写"算过"。**

---

## 6. 自检怎么用

```bash
python scripts/preflight.py --artifacts <项目>/out/cigar --plans <项目>/data/plans
```

检查项：markdown 残留、章节引用、空白页、图幅（按**实际版心**判定）、同批色阶一致、低可信材质。

**0 FAIL 才能交付。** WARN 需人工看一眼。

---

## 7. 迭代方式

建议每个项目结束后只更新一处：`SKILL.md` §4「反模式」表。
**新增一条反模式 = 一次真实踩坑**，比写十条"最佳实践"有用。

版本号写在 `SKILL.md` 第 3 行；`AGENTS.md` 引用版本号，避免两者脱节。

---

## 8. 已验证的真实案例

本技能的流程来自一个真实项目（雪茄吧四间包房）：

- 真实网格约 47 万三角面，oconv 15 s，rtrace 0.14 s/点
- 用"单位光通贡献率"量出：洗墙对座位的效率是铜顶灯槽的 **4.2 倍**
- 四间交叉验证：房一算 54.6 lx，既有汇总 54.7 lx（差 0.2%）
- 自检 31 项，0 FAIL
- 期间踩的 7 个坑全部收进 §4 反模式表
