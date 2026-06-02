# act_train_platform 打包与现场部署说明

## 一键打包

在开发机 PowerShell 中执行：

```powershell
cd "D:\soft\99 AllWorkSpace\action_detection\act_train_platform"
.\scripts\package_act_train_platform.ps1
```

如果 PowerShell 禁止执行脚本，可只对当前命令临时放开：

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\package_act_train_platform.ps1"
```

打包输出目录：

```text
D:\soft\99 AllWorkSpace\action_detection\act_train_platform\dist\act_train_platform
```

## 现场目录规则

部署目录不再要求固定盘符。只要求整体目录结构保持为：

```text
任意盘:\act_det\
  act_train_platform\
    act_train_platform.exe
    data\
```

例如可以是：

```text
E:\act_det\act_train_platform
D:\act_det\act_train_platform
```

程序启动后会以 `act_train_platform.exe` 所在目录作为项目根目录，运行数据默认使用同级 `data\`。

## 启动命令

```powershell
.\act_train_platform.exe --host 0.0.0.0 --port 18100
```

浏览器访问：

```text
http://127.0.0.1:18100/
```

局域网其他电脑访问时，将 `127.0.0.1` 换成部署电脑 IP。

## 数据复制清单

打包程序本身不包含开发机历史运行数据。需要迁移历史数据时，复制 `data\` 下的对应目录：

必须复制：

- `data\act_train_platform.sqlite3`
- `data\datasets`
- `data\packages`

继续标注旧帧集时复制：

- `data\frames`
- `data\uploads`
- `data\assets`

查看历史训练任务或历史训练曲线时复制：

- `data\runs`

如果只更新程序版本，且现场数据已经在公共机上，不要每次覆盖整个 `data\`。只复制新的打包程序文件，保留现场 `data\`。

## 路径可搬迁说明

历史数据中可能保存过开发机绝对路径，例如：

```text
D:\soft\99 AllWorkSpace\action_detection\act_train_platform\data\...
```

从 `v1.2.1.2` 开始，平台启动时会自动修复可安全识别的平台内部路径，并在读取训练数据集、帧图片、模型包、训练输出时映射到当前机器的 `data\` 目录。

外部导入的任意本地路径不会被自动改写；这类路径需要用户在新机器上重新选择或重新导入。

## 训练子进程

打包版训练任务会通过内部命令启动：

```text
act_train_platform.exe --train-worker <job_id>
```

这是平台内部使用的入口，现场用户不需要手动执行。
