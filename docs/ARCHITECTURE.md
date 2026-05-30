# act_train_platform 架构说明

## 1. 系统边界

`act_train_platform` 是行为检测系统的模型生产端，负责从现场视频生成训练数据集、训练模型并导出可部署模型包。它不参与产线实时推理、SOP 报警判断、摄像头会话管理、AOI 运行规则或硬件联动。

```mermaid
flowchart LR
  Video["现场视频"] --> Train["act_train_platform"]
  Train --> Dataset["训练数据集版本"]
  Dataset --> Package["模型包目录"]
  Package --> Server["act_server"]
  Server --> Web["act_web"]
```

## 2. 模块职责

- `app.py`：命令行入口和兼容 ASGI 入口。
- `web/app_factory.py`：创建 FastAPI 应用、挂载模板和静态文件、注册路由。
- `web/routes/`：HTTP 页面和 API 路由，按标签/产品、视频/抽帧、标注、数据集、训练、模型仓库分组。
- `core/repositories/`：SQLite 读写。`core.store` 是兼容 facade，旧调用可继续使用。
- `core/datasets/`：数据集导出、关注区域裁剪、历史数据集混入、图片尺寸统计和推荐输入尺寸。
- `core/media/`：素材库、视频导入、产品视频复制、抽帧。
- `core/annotation/`：标注插值、预标注、预标注确认和清空。
- `core/training/`：训练任务、训练进度、GPU 状态、模型包生成。
- `static/js/annotate/`、`static/js/datasets/`：页面级前端实现；根入口脚本只负责 bootstrap。

## 3. 数据边界

SQLite 保存业务元数据：

- `labels`：A/B/C 标签字典。
- `projects`：产品配置，底层仍使用历史表名。
- `video_assets`、`videos`：全局素材库与产品视频副本。
- `frame_sets`、`frames`：抽帧任务和帧文件索引。
- `focus_regions`：关注区域，用于训练/推理裁剪视野。
- `tracks`、`annotations`：标注框、关键帧、轨迹、预标注。
- `dataset_versions`：不可变训练数据集版本。
- `train_jobs`：训练任务。
- `model_packages`：导出的模型包目录。

视频、帧图片、训练数据集、训练输出和模型包继续存放在 `data/` 目录，不进入 SQLite。

## 4. 兼容策略

`v1.2.0.0` 是架构治理版本，不改变 API 路径、SQLite schema、文件目录语义或客户可见业务流程。旧模块名至少保留一个小版本：

- `core.store`
- `core.dataset_ops`
- `core.video_ops`
- `core.annotation_ops`
- `core.prelabel_ops`
- `core.training_ops`

新代码应优先写入对应领域包，不再继续把所有实现堆到 `app.py`、`core/store.py` 或单个页面脚本中。
