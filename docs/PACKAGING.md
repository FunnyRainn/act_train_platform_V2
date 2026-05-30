# act_train_platform 打包说明

## 一键打包

在 PowerShell 中执行：

```powershell
cd "D:\soft\99 AllWorkSpace\action_detection\act_train_platform"
.\scripts\package_act_train_platform.ps1
```

如果 PowerShell 提示禁止运行脚本，可只对当前命令临时放开：

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\package_act_train_platform.ps1"
```

## 输出目录

打包完成后输出到：

```text
D:\soft\99 AllWorkSpace\action_detection\act_train_platform\dist\act_train_platform
```

目标机器启动：

```powershell
.\act_train_platform.exe --host 0.0.0.0 --port 18100
```

浏览器访问：

```text
http://127.0.0.1:18100/
```

## 打包内容

脚本会打入：

- FastAPI 服务入口。
- `static/` 页面资源。
- `templates/` 页面模板。
- `docs/` 使用说明。
- SQLite 初始化脚本 `core/schema.sql`。
- 当前目录下的基础模型文件 `*.pt`，例如 `yolo11m.pt`、`yolo26n.pt`。
- 空的 `data/` 运行目录结构。

脚本不会打入当前开发机已有的运行数据：

- `data/act_train_platform.sqlite3`
- 上传视频。
- 抽帧图片。
- 数据集版本。
- 训练运行目录。
- 模型包目录。

部署时如果要迁移历史数据，需要单独复制 `data/` 目录。

## 训练子进程

打包版训练任务会通过：

```text
act_train_platform.exe --train-worker <job_id>
```

启动内部训练子进程。这个入口只给平台内部使用，现场用户不需要手动执行。
