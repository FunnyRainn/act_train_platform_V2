"""显式高级训练参数白名单；不改变省略字段的旧行为，不静默忽略有界修正配置。"""
import math


def advanced_training_kwargs(params: dict) -> dict:
    """创建任务和启动worker时共同验证；小数据集可显式缩小梯度累积或关闭拼图增强。"""
    result = {}
    if "optimizer" in params:
        optimizer = str(params["optimizer"])
        if optimizer not in {"auto", "SGD", "Adam", "AdamW"}:
            raise ValueError("optimizer必须为auto/SGD/Adam/AdamW")
        result["optimizer"] = optimizer
    for key, lower, upper in [("lr0", 0, 1), ("mosaic", 0, 1), ("warmup_epochs", 0, 100)]:
        if key not in params:
            continue
        value = float(params[key])
        if isinstance(params[key], bool) or not math.isfinite(value) or not lower <= value <= upper or (key == "lr0" and value == 0):
            raise ValueError(f"{key}超出有效范围")
        result[key] = value
    if "nbs" in params:
        value = params["nbs"]
        if isinstance(value, bool) or float(value) != int(value) or not 1 <= int(value) <= 1024:
            raise ValueError("nbs必须为1—1024的整数")
        result["nbs"] = int(value)
    return result
