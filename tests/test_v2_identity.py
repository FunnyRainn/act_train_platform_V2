from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app as app_module
from web.app_factory import VERSION, create_app


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class V2IdentityTests(unittest.TestCase):
    """锁定训练平台的 V2 版本、独立端口和独立环境入口。"""

    def test_runtime_version_default_port_and_version_route_are_v2(self) -> None:
        """训练平台必须在 28100 启动，并通过只读端点报告统一 V2 版本。"""

        self.assertEqual(VERSION, "V2.0.0.0")
        args = SimpleNamespace(host="127.0.0.1", port=28100, train_worker=None)
        with (
            patch.object(app_module.argparse.ArgumentParser, "parse_args", return_value=args),
            patch.object(app_module.uvicorn, "run") as run,
        ):
            app_module.main()
        run.assert_called_once_with(app_module.app, host="127.0.0.1", port=28100, reload=False)

        application = create_app()
        version_route = next(route for route in application.routes if getattr(route, "path", "") == "/version")
        self.assertEqual(version_route.endpoint(), {"version": "V2.0.0.0"})

    def test_source_launcher_uses_v2_environment_and_port(self) -> None:
        """双击源码入口不得激活 V1 环境或占用 V1 Train 端口。"""

        launcher = (PROJECT_ROOT / "启动act_train_platform源码.cmd").read_text(encoding="utf-8")
        self.assertIn("act_server_py310_V2", launcher)
        self.assertIn("--port 28100", launcher)
        self.assertNotIn("--port 18100", launcher)


if __name__ == "__main__":
    unittest.main()
