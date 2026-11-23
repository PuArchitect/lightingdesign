# Windows 运行注意（v2.5.0）

## 1. 用真实的 Python

Microsoft Store 的 `python` 可能是别名，`where python` 会看到 `WindowsApps`。
优先用：

```powershell
py -3 --version
# 或
& "C:\Path\To\Python\python.exe" --version
```

## 2. 路径带空格必须加引号

```powershell
python "D:\My Work\lightingdesign\scripts\00_preflight_env.py" --project-id demo --out "D:\My Work\work\env_fingerprint.json"
```

## 3. RAYPATH

`00_preflight_env.py` 会写 `radiance_env` 与 `radiance_smoke`。
冒烟值应接近 `2.176 W/m²`；若返回 `1,1,1`，说明 RAYPATH 缺 `lib`，能力会锁 L2。

## 4. 浏览器打印

`05_build_report_pdf.py` 需要 Chrome/Edge。沙箱/无浏览器时用 Story 路径（`scripts/tools/report_story_room4.py`）或 `svg_to_a3_pdf.py`。
