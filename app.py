from __future__ import annotations

import argparse
import multiprocessing

import uvicorn

from core.db import init_db
from web.app_factory import VERSION, create_app

app = create_app()


def main() -> None:
    """用途：说明 应用入口、命令行启动和训练 worker 分派 中 `main` 的职责和调用边界。
    入参：无。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能解析启动参数、启动 Web 服务或执行训练 worker。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    parser = argparse.ArgumentParser(description="Start act_train_platform")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18100)
    parser.add_argument("--train-worker", help="internal training worker job id")
    args = parser.parse_args()
    if args.train_worker:
        from core import train_worker

        init_db()
        train_worker.run(args.train_worker)
        return
    uvicorn.run(app, host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
