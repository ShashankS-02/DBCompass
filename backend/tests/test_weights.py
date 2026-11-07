"""Tests for slider-to-weight conversion."""

import pytest

from app.engine.weights import compute_dimension_weights
from app.models.questions import PrioritySlider


def make_sliders() -> list[PrioritySlider]:
    sliders = []
    for slider_id, dimension in [("speed", "performance"), ("price", "cost")]:
        sliders.append(
            PrioritySlider(id=slider_id, label=slider_id, dimension=dimension, default=50, description="")
        )
    return sliders


def test_sliders_share_what_fixed_weights_leave() -> None:
    weights = compute_dimension_weights({"speed": 100, "price": 0}, make_sliders(), {"ecosystem": 0.2})

    assert weights == {"performance": 0.8, "cost": 0.0, "ecosystem": 0.2}


def test_missing_slider_uses_its_default() -> None:
    weights = compute_dimension_weights({"speed": 50}, make_sliders(), {})

    assert weights == {"performance": 0.5, "cost": 0.5}


def test_all_sliders_at_zero_split_equally() -> None:
    weights = compute_dimension_weights({"speed": 0, "price": 0}, make_sliders(), {"ecosystem": 0.2})

    assert weights == {"performance": 0.4, "cost": 0.4, "ecosystem": 0.2}


def test_weights_sum_to_one() -> None:
    weights = compute_dimension_weights({"speed": 33, "price": 71}, make_sliders(), {"ecosystem": 0.1})

    assert sum(weights.values()) == pytest.approx(1.0, abs=1e-3)


def test_fixed_weights_above_one_are_rejected() -> None:
    with pytest.raises(ValueError):
        compute_dimension_weights({}, make_sliders(), {"ecosystem": 0.7, "compliance": 0.4})
