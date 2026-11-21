# Windows 上怎么跑（给同事的第一道坎）

> 文档里那些 ```` ```bash ```` 代码块只是**记号**，不是要你装 Linux。
> Windows 上照抄命令内容，用下面的窗口输入即可。

---

## 一、用哪个窗口

| 窗口 | 能不能用 | 说明 |
|---|---|---|
| **PowerShell**（推荐） | ✅ | `Win + X` → 选「终端」或「Windows PowerShell」 |
| **Git Bash** | ✅ | 装了 Git 就有：开始菜单搜 "Git Bash"；命令与文档几乎一致 |
| **cmd（命令提示符）** | ⚠️ | 命令能跑，但**环境变量语法不同**，容易踩坑 |

**推荐 PowerShell**：本仓库文档里的环境变量写法（`$env:XXX='值'`）就是 PowerShell 语法。

---

## 二、三步跑起来

在 PowerShell 里：

```powershell
# 1. 进到你想放仓库的目录（示例）
cd D:\工作文档

# 2. 克隆
git clone https://github.com/PuArchitect/lightingdesign.git
cd lightingdesign

# 3. 自举
python scripts/bootstrap.py
```

---

## 三、⚠️ 最大的坑：你的 `python` 可能是假的

Windows 上有个「应用执行别名」：即使**没装 Python**，敲 `python` 也会"成功"，
实际是打开 Microsoft Store，或者报一句 `Python was not found`。

**先验一下**：

```powershell
python --version
where.exe python
```

判断标准：

| 现象 | 含义 | 怎么办 |
|---|---|---|
| 打印出 `Python 3.x.x` | ✅ 真 Python | 继续 |
| 弹出 Microsoft Store | ❌ 没装 Python | 见下方安装 |
| `Python was not found` | ❌ 同上 | 见下方安装 |
| `where` 结果显示 `...\WindowsApps\python.exe` | ❌ 商店占位程序 | 见下方安装 |

### 安装真 Python（二选一）

```powershell
# 方式 A：winget（Win10 1809+ 自带）
winget install -e --id Python.Python.3.12
```

方式 B：去 <https://www.python.org/downloads/windows/> 下载安装包，
**安装第一屏务必勾选 `Add python.exe to PATH`**，否则装完还是敲不出来。

装完**关掉窗口重开**，再验一次 `python --version`。

---

## 四、环境变量：三种窗口三种写法

本仓库用到的只有 `LIGHTINGDESIGN_FORCE_LEVEL`（测试降级用）和 `RAYPATH`。

| 窗口 | 临时设置（只对当前窗口有效） | 清除 |
|---|---|---|
| **PowerShell** | `$env:RAYPATH = "C:\path\bin;."` | `Remove-Item Env:\RAYPATH` |
| **Git Bash** | `export RAYPATH="/c/path/bin:."` | `unset RAYPATH` |
| **cmd** | `set RAYPATH=C:\path\bin;.` | `set RAYPATH=` |

> `RAYPATH` 是 Radiance 找参数文件用的。不配它，`rtrace` 会对每条光线返回 `1,1,1` ——
> **给出看起来合理、实际全错的数**。`bootstrap.py` 会把该配的值直接打印出来，复制即可。

永久生效（PowerShell）：`setx RAYPATH "C:\path\bin;."`，然后**重开窗口**。

---

## 五、常见报错对照

| 报错 | 原因 | 解决 |
|---|---|---|
| `python: 无法将“python”项识别为…` | Python 没装 / 没进 PATH | 见第三节 |
| 弹出 Microsoft Store | 商店占位程序 | 见第三节 |
| `'git' 不是内部或外部命令` | 没装 Git | 装 Git for Windows |
| `ModuleNotFoundError: No module named 'PIL'` | 缺包 | `python scripts/bootstrap.py --install --yes` |
| `error: could not read Username` | 克隆私有仓库 | 本仓库是公开的，重新核对 URL |
| `bash: python: command not found`（Git Bash） | Git Bash 不继承 PATH | 在 Git Bash 里用 `py` 或完整路径，或改用 PowerShell |

---

## 六、一句话

**用 PowerShell，先验 `python --version` 是真的，再 `git clone`，最后 `bootstrap.py`。**
看到 Microsoft Store 弹出来，就是没装 Python —— 那不是技能的问题。
