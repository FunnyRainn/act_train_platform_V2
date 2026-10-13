"""数据集短文件名回归：只写临时目录，不访问真实训练库。"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from core.datasets.filenames import DatasetFilenames, validate_target, windows_read_path


class DatasetFilenameTests(unittest.TestCase):
    def test_repeated_prefix_and_duplicate_stems_are_bounded_and_paired(self):
        """来源名称再长也不参与输出名；同名不同来源不能覆盖。"""
        with TemporaryDirectory() as tmp:
            names = DatasetFilenames(Path(tmp))
            pairs = [names.allocate("train", suffix) for suffix in (".JPG", ".png", ".jpg")]
            for index, (image, label) in enumerate(pairs):
                self.assertEqual(image.stem, label.stem)
                self.assertLessEqual(len(image.name), 20)
                names.record(image, "train", "dataset_old", "dataset_abc__" * 8 + f"图{index}.jpg")
            self.assertEqual(len({image.stem for image, _ in pairs}), 3)
            names.save()
            records = json.loads((Path(tmp) / "filename_map.json").read_text(encoding="utf-8"))
            self.assertEqual(len(records["files"]), 3)
            self.assertIn("dataset_abc__", records["files"][0]["source_relative_path"])

    def test_existing_output_cannot_be_overwritten(self):
        """对已存在的图片或标签同时避让，防止扩展名差异造成标签覆盖。"""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            existing = root / "labels/train/img_00000001.txt"
            existing.parent.mkdir(parents=True)
            existing.write_text("old", encoding="utf-8")
            image, label = DatasetFilenames(root).allocate("train", ".jpg")
            self.assertNotEqual(label, existing)
            self.assertEqual(existing.read_text(), "old")

    def test_windows_budget_rejects_before_writing(self):
        """不能通过缩短文件名解决的根路径明确拒绝，不截断目录。"""
        target = Path("/" + "a" * 230)
        with patch("core.datasets.filenames.os.name", "nt"):
            with self.assertRaisesRegex(ValueError, "路径过长"):
                validate_target(target)

    def test_non_windows_source_is_unchanged(self):
        """非Windows读取路径不得意外加Windows前缀。"""
        source = Path("/tmp/中文/图片.jpg")
        with patch("core.datasets.filenames.os.name", "posix"):
            self.assertEqual(windows_read_path(source), source)

    def test_import_and_repeated_history_merge_preserve_pairs_classes_and_split(self):
        """调用真实导入和历史复制，隔离配置仓库；验证短名不是只在辅助函数中生效。"""
        import cv2
        import numpy as np
        from core.datasets import yolo_importer as importer, exporter
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "客户原始包"
            original_name = "dataset_old__" * 10 + "原图"
            for split in ("train", "val", "test"):
                for folder in ("images", "labels"):
                    (source / folder / split / "子目录").mkdir(parents=True)
                image = source / "images" / split / "子目录" / (original_name + ".jpg")
                cv2.imwrite(str(image), np.zeros((16, 16, 3), dtype=np.uint8))
                (source / "labels" / split / "子目录" / (original_name + ".txt")).write_text("0 0.5 0.5 0.2 0.2")
            (source / "data.yaml").write_text("train: images/train\nval: images/val\ntest: images/test\nnames: [外部标签]\n", encoding="utf-8")
            before = {p.relative_to(source).as_posix(): p.read_bytes() for p in source.rglob("*") if p.is_file()}
            with patch.object(importer, "DATASETS_DIR", root / "generated"), patch.object(importer.store, "get_project", return_value={"label_codes": ["A1"]}), patch.object(importer.store, "save_dataset_version", side_effect=lambda item: item):
                dataset = importer.import_yolo_dataset("project_test", "隔离导入", str(source), {"0": "A1"})
            for iteration in range(3):
                output = root / f"merge{iteration}"
                names = DatasetFilenames(output)
                images = {s: output / "images" / s for s in ("train", "val", "test")}
                labels = {s: output / "labels" / s for s in images}
                for directory in [*images.values(), *labels.values()]:
                    directory.mkdir(parents=True)
                counts = dict.fromkeys([*images, "skipped_history_missing_label", "skipped_history_empty_label", "history_images", "history_boxes", "boxes"], 0)
                counts["history_sources"] = []
                exporter._copy_history_dataset(dataset, images, labels, {"A1": 0}, counts, exporter._new_size_stats(), names)
                names.save()
                self.assertEqual(counts["history_images"], 3)
                self.assertEqual(len(names.files), 3)
                for split in images:
                    files = list(images[split].glob("*.jpg"))
                    self.assertEqual(len(files), 1)
                    self.assertLess(len(files[0].name), 22)
                    self.assertEqual((labels[split] / (files[0].stem + ".txt")).read_text(), "0 0.5 0.5 0.2 0.2")
                dataset = {"id": f"history_{iteration}", "name": "历史合并", "output_dir": str(output), "label_codes": ["A1"]}
            self.assertEqual(before, {p.relative_to(source).as_posix(): p.read_bytes() for p in source.rglob("*") if p.is_file()})


if __name__ == "__main__":
    unittest.main()
