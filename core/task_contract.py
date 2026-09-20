"""V2.4三任务共同合同；三组件保持同源内容，由总控一致性测试检查。"""

from __future__ import annotations

from pathlib import Path, PureWindowsPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

TaskType = Literal["detect", "instance_segment", "semantic_segment"]
ULTRALYTICS_TASKS = {"detect": "detect", "instance_segment": "segment", "semantic_segment": "semantic"}
TASK_CAPABILITIES = {
    "detect": frozenset({"objects", "boxes", "count", "track"}),
    "instance_segment": frozenset({"objects", "boxes", "count", "track", "mask"}),
    "semantic_segment": frozenset({"mask", "class_map"}),
}
OUTPUT_LAYOUTS = {
    "detect": {"ultralytics_boxes", "yolo_raw", "yolo_end2end"},
    "instance_segment": {"ultralytics_instances", "yolo_mask_prototypes", "yolo_end2end_masks"},
    "semantic_segment": {"ultralytics_semantic", "semantic_logits", "semantic_class_map"},
}

# 此目录是跨组件共享合同的一部分；Train派生下载来源，其余组件不维护第二套型号表。
MODEL_PROFILES = tuple(
    {"id": name + suffix, "name": name + suffix, "size": size, "label": label,
     "task_type": task, "default": size == "small"}
    for size, label, name in (("small", "小模型", "PieV2S"), ("medium", "中模型", "PieV2M"),
                              ("large", "大模型", "PieV2L"), ("general", "通用模型", "PieV1M"))
    for task, suffix in (("detect", ""), ("instance_segment", "_Seg"), ("semantic_segment", "_Sem"))
    if not (size == "general" and task == "semantic_segment")
)
PIE_LAYOUTS = {"detect": "objects_v1", "instance_segment": "instances_v1", "semantic_segment": "class_map_v1"}
PIE_BACKEND_LAYOUTS = {"objects_v1": "ultralytics_boxes", "instances_v1": "ultralytics_instances",
                       "class_map_v1": "ultralytics_semantic"}


def model_profile(profile_id: str | None, task: str) -> dict:
    """稳定ID必须与数据集任务一致；省略时仅为新请求选择小模型。"""
    task_type(task)
    matches = [row for row in MODEL_PROFILES if row["task_type"] == task
               and (row["id"] == profile_id if profile_id else row["default"])]
    if len(matches) != 1:
        raise ValueError("型号不存在或与数据集任务不匹配")
    return dict(matches[0])


def task_type(value: str) -> TaskType:
    """拒绝未知类型，不根据权重文件名猜测任务。"""
    if value not in ULTRALYTICS_TASKS:
        raise ValueError(f"不支持的任务类型: {value}")
    return value


def require_task_match(*values: str) -> str:
    """数据、训练、模型三者必须同任务，禁止隐式转换。"""
    tasks = [task_type(value) for value in values]
    if not tasks or len(set(tasks)) != 1:
        raise ValueError(f"任务类型不匹配: {', '.join(tasks)}")
    return tasks[0]


class TaskContract(BaseModel):
    """新包必须携带的可移植合同；不接受拼错字段或未知版本。"""

    model_config = ConfigDict(extra="forbid")
    contract_version: Literal[1, 2] = 1
    task_type: TaskType
    model_family: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    label_map: dict[int, str]
    input_hw: tuple[int, int]
    input_channels: Literal[3] = 3
    color_order: Literal["RGB"] = "RGB"
    output_layout: str
    coordinate_space: Literal["original_image"] = "original_image"
    background_id: int | None = None
    ignore_id: int | None = None

    @property
    def backend_output_layout(self) -> str:
        """内部适配时解析公开布局，不在包里泄漏第三方高层结果名称。"""
        return PIE_BACKEND_LAYOUTS.get(self.output_layout, self.output_layout)

    @model_validator(mode="after")
    def validate_contract(self):
        """布局与任务一致；类别索引连续；语义背景和忽略不得混淆。"""
        if self.contract_version == 2:
            if self.model_family != "PieCustom":
                model_profile(self.model_family, self.task_type)
            if self.output_layout != PIE_LAYOUTS[self.task_type]:
                raise ValueError("Pie合同布局与任务不匹配")
        else:
            if not self.model_family.lower().startswith("yolo"):
                raise ValueError("旧版合同模型家族不受支持")
            if self.output_layout not in OUTPUT_LAYOUTS[self.task_type]:
                raise ValueError("输出布局与任务不匹配")
        if not self.label_map or sorted(self.label_map) != list(range(len(self.label_map))):
            raise ValueError("类别映射必须是从0开始的连续索引")
        if any(not value.strip() for value in self.label_map.values()) or len(set(self.label_map.values())) != len(self.label_map):
            raise ValueError("类别名称不得为空或重复")
        if any(size <= 0 or size % 32 for size in self.input_hw):
            raise ValueError("输入高宽必须为正的32倍数")
        if self.task_type == "semantic_segment":
            if self.background_id not in self.label_map:
                raise ValueError("语义模型必须明确背景类别")
            if self.ignore_id is None or self.ignore_id < 0 or self.ignore_id in self.label_map:
                raise ValueError("忽略像素值必须独立于有效类别")
        elif self.background_id is not None or self.ignore_id is not None:
            raise ValueError("对象任务不能声明语义背景/忽略值")
        return self


def parse_manifest_contract(manifest: dict) -> TaskContract | None:
    """缺少新合同只兼容旧检测；部分新字段存在时不能假装旧包。"""
    raw = manifest.get("task_contract")
    if raw is None:
        if manifest.get("task_type", "detect") != "detect" or "contract_version" in manifest:
            raise ValueError("新任务模型包缺少完整task_contract")
        return None
    contract = TaskContract.model_validate(raw)
    if manifest.get("task_type", contract.task_type) != contract.task_type:
        raise ValueError("模型包任务声明冲突")
    labels = manifest.get("label_codes")
    if labels is not None and [contract.label_map[index] for index in range(len(contract.label_map))] != labels:
        raise ValueError("模型包标签与合同不一致")
    return contract


def package_weight_path(root: Path, name: str) -> Path:
    """跨平台拒绝绝对路径、越界、符号链接逃逸，避免读入包外权重。"""
    relative = Path(name)
    windows = PureWindowsPath(name)
    if relative.is_absolute() or windows.is_absolute() or windows.drive or ".." in windows.parts or ".." in relative.parts:
        raise ValueError("模型包权重必须是包内相对路径")
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("模型包权重越出包目录")
    return target


def require_capability(task: str, capability: str) -> None:
    """配置发布时明确拒绝不具备对象/区域/身份能力的任务。"""
    if capability not in TASK_CAPABILITIES[task_type(task)]:
        raise ValueError(f"{task}不支持{capability}能力")
