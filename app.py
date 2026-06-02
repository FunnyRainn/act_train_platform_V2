from __future__ import annotations

import argparse

import uvicorn

from core.db import init_db
from web.app_factory import VERSION, create_app

app = create_app()


def main() -> None:
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
    main()
