# golden

- `check_delivery.py`：交付目录硬校验（房间尺寸/级别/清单/A3/成品自检/目标口径/面积出处）。
- `deliverable_manifest.template.json`：新样本 manifest 模板。
- `manifests/S1–S4`：历史对比样本；路径为相对路径，需在对应工作区运行。

用法：
```powershell
python golden/check_delivery.py <交付目录> --manifest golden/manifests/<样本>.json --project project/project_room4_雪茄吧.json
```
