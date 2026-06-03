# act_train_platform 使用说明

## 1. 启动环境

第一版直接使用已经具备训练依赖的 conda 环境运行。当前本机验证可用环境为：

```text
conda activate act_server_py310
```

如果后续你确认 `train_act_det_yolo` 使用的是另一个训练环境，则把下面命令中的 Python 路径替换成该环境的 `python.exe`。

启动命令：

```powershell
cd act_train_platform
conda activate act_server_py310
python app.py --host 0.0.0.0 --port 18100
```

访问：

```text
http://127.0.0.1:18100/
```

## 2. 基础操作流程

1. 打开“标签字典”，创建本次训练需要的 `A/B/C` 标签。
2. 每个标签都填写“框选说明”，例如 `C1 tray` 要框完整 tray 外接矩形。
3. 打开“训练项目”，创建项目并选择标签。
4. 打开“视频与抽帧”，上传视频或填写服务器本地视频路径导入。
5. 对视频执行抽帧，生成帧集。
6. 打开“标注工作台”，选择帧集后开始画框。
7. 如果同一个对象跨多帧出现，创建轨迹 ID，在关键帧上标注并勾选“当前框为关键帧”。
8. 至少保存两个关键帧后，点击“按轨迹插值”生成中间帧 bbox。
9. 如已有旧模型，可填写模型路径并运行预标注；预标注框默认是待确认状态。
10. 打开“数据集版本”，选择帧集导出 YOLO 数据集。
11. 打开“训练任务”，选择数据集版本和基础模型启动训练。
12. 训练完成后打开“模型包”，导出可复制到 `act_server` 的模型包。

## 3. 数据目录

```text
data/
├── uploads/       # 上传视频
├── imports/       # 预留导入目录
├── frames/        # 抽帧结果
├── datasets/      # YOLO 数据集版本
├── runs/          # 训练输出
├── packages/      # 模型包
├── prelabels/     # 预标注中间结果
└── act_train_platform.sqlite3
```

## 4. 模型包交付

模型包目录会包含：

```text
best.pt
labels.yaml
package.json
train_report.json
dataset_version.json
preview_examples/
```

第一阶段不做网络分发。导出后人工复制到推理服务器，例如：

```text
D:\poioeo_ai_server\models\某模型包\
```

然后在 `act_server` 侧配置使用该 `best.pt`。

## 5. 注意事项

- 新产品训练时，如果不混入历史数据集，平台会提示风险，但不会强制阻止。
- 预标注只是降低标注成本，不能替代人工确认。
- A/B/C 标签编码一旦进入训练数据，不建议随意改含义。
- 当前只支持 bbox 检测数据，不支持分割和姿态。
