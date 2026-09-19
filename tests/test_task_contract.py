"""三组件共同合同的正反例；不导入CUDA、Torch或应用生命周期。"""
from pathlib import Path
import tempfile
import unittest
from core.task_contract import TaskContract, parse_manifest_contract, package_weight_path, require_capability, require_task_match


class TaskContractTests(unittest.TestCase):
    def make(self, task="detect"):
        """构造最小显式合同，标签包含可区分的背景及对象。"""
        return dict(task_type=task, model_family="yolo26", model_version="test-sha", label_map={0:"background",1:"tie"}, input_hw=(64,64), output_layout={"detect":"ultralytics_boxes","instance_segment":"ultralytics_instances","semantic_segment":"semantic_class_map"}[task], **({"background_id":0,"ignore_id":255} if task=="semantic_segment" else {}))

    def test_three_tasks(self):
        for task in ("detect","instance_segment","semantic_segment"):
            self.assertEqual(TaskContract(**self.make(task)).task_type, task)

    def test_legacy_only_detect(self):
        self.assertIsNone(parse_manifest_contract({"label_codes":["A1"]}))
        with self.assertRaises(ValueError):
            parse_manifest_contract({"task_type":"instance_segment"})

    def test_layout_and_class_map_constraints(self):
        values=self.make("semantic_segment")
        for change in ({"output_layout":"yolo_raw"}, {"ignore_id":0}, {"background_id":8}, {"input_hw":(63,64)}, {"contract_version":2}):
            with self.assertRaises(ValueError):
                TaskContract(**(values|change))

    def test_task_and_capability_mismatch(self):
        with self.assertRaises(ValueError):
            require_task_match("detect","instance_segment")
        for capability in ("count","track","objects"):
            with self.assertRaises(ValueError):
                require_capability("semantic_segment", capability)
        require_capability("instance_segment","track")

    def test_manifest_labels_must_match(self):
        with self.assertRaises(ValueError):
            parse_manifest_contract({"task_contract":self.make(), "label_codes":["different"]})

    def test_portable_package_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/"package"
            root.mkdir()
            self.assertEqual(package_weight_path(root,"best.pt"), (root/"best.pt").resolve())
            for name in ("../best.pt", "/tmp/best.pt", "C:\\models\\best.pt", "..\\best.pt"):
                with self.assertRaises(ValueError):
                    package_weight_path(root,name)
            (root/"link").symlink_to(Path(temp))
            with self.assertRaises(ValueError):
                package_weight_path(root,"link/other.pt")


if __name__=="__main__":
    unittest.main()
