from __future__ import annotations

import unittest

from core.train_worker import _worker_count


class MacTrainingDeviceTests(unittest.TestCase):
    def test_mps_defaults_to_in_process_data_loading(self) -> None:
        self.assertEqual(_worker_count({"device": "mps"}), 0)
        self.assertEqual(_worker_count({"device": " MPS "}), 0)

    def test_explicit_worker_count_still_wins(self) -> None:
        self.assertEqual(_worker_count({"device": "mps", "workers": 2}), 2)


if __name__ == "__main__":
    unittest.main()
