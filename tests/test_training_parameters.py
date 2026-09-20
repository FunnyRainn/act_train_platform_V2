"""小样本定向修正参数显式透传，零值和非法值不得被默认值吞掉。"""
import pytest
from core.training.parameters import advanced_training_kwargs


def test_optional_parameters_and_zero_mosaic():
    assert advanced_training_kwargs({}) == {}
    values = {"optimizer": "AdamW", "lr0": .001, "nbs": 2, "mosaic": 0, "warmup_epochs": 1}
    assert advanced_training_kwargs(values) == values


@pytest.mark.parametrize("values", [{"lr0": 0}, {"lr0": float("nan")}, {"nbs": 0}, {"nbs": 1.5},
    {"mosaic": -1}, {"warmup_epochs": -1}, {"optimizer": "unknown"}, {"nbs": True}])
def test_invalid_parameters_rejected(values):
    with pytest.raises(ValueError):
        advanced_training_kwargs(values)
