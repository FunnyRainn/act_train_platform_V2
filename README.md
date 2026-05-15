# act_train_platform

## v1.0.0.2 Notes

- Training forms keep the selected product, dataset, and task fields while the page refreshes.
- Training charts show visible legends and help text.
- Finished or stopped training jobs automatically create deployable model directories when model files exist.
- The model repository is now a repository view; operators no longer need to manually generate the model directory.
- The overview page shows the full production flow from labels to model repository.

行为检测项目的标注训练平台。

这个项目是“模型生产端”，面向客户的集中训练服务器。它和产线实时使用的 `act_web`、推理服务 `act_server` 分开部署。

## 1. 项目定位

`act_train_platform` 用来完成：

- 导入生产视频。
- 抽取训练帧。
- 维护 `A* / B* / C*` 标签字典。
- 在网页中标注 bbox。
- 使用关键帧和轨迹插值降低重复标注工作量。
- 使用旧模型进行可选预标注。
- 导出 YOLO 数据集版本。
- 启动 YOLO 训练。
- 导出可人工复制到 `act_server` 的模型包。

它不负责实时推理、不负责摄像头会话、不负责 SOP 报警、不负责 AOI 运行时规则。

## 2. 环境

第一版直接使用 `train_act_det_yolo` 当前训练环境运行，复用已经安装好的 GPU 版 Torch、Ultralytics、OpenCV 等依赖。

建议在该环境中补齐 Web 依赖：

```powershell
pip install -r requirements.txt
```

## 3. 启动

```powershell
python app.py --host 0.0.0.0 --port 18100
```

浏览器访问：

```text
http://127.0.0.1:18100/
```

## 4. 第一版推荐流程

1. 在“标签字典”中创建 `A/B/C` 标签，并填写框选说明。
2. 在“训练项目”中创建项目，选择本次训练用到的标签。
3. 在“视频与抽帧”中上传视频，或从服务器目录导入视频。
4. 创建抽帧任务，得到可标注帧集。
5. 在“标注工作台”中标注关键帧，使用插值生成中间帧。
6. 可选：选择旧模型执行预标注，再人工确认。
7. 在“数据集版本”中导出 YOLO 数据集。
8. 在“训练任务”中创建训练任务。
9. 训练完成后在“模型包”中导出标准模型包。
10. 人工复制模型包到 `act_server` 推理服务器。

## 5. 模型包内容

```text
model_package/
├── best.pt
├── labels.yaml
├── package.json
├── train_report.json
├── dataset_version.json
└── preview_examples/
```

## 6. 标签原则

- `A*`：正常流程动作或状态。
- `B*`：异常事件或异常状态。
- `C*`：物理对象，例如 tray、湿度卡、手、工件。

每个标签必须写清楚“到底框什么”。例如：

- `C1 tray`：框住完整 tray 外接矩形。
- `C2 湿度卡`：框住湿度卡可见外接矩形。
- `C3 手`：框住单只手的可见区域。

如果标签说明不清楚，不同标注员会框不同对象，训练出来的模型会不稳定。
