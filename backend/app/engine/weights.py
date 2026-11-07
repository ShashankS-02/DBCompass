"""Turn priority slider positions into scoring dimension weights (OPEN_QUESTIONS #2)."""

from app.models.questions import PrioritySlider

WEIGHT_DECIMALS = 4


def compute_dimension_weights(
    slider_values: dict[str, int],
    sliders: list[PrioritySlider],
    fixed_dimension_weights: dict[str, float],
) -> dict[str, float]:
    """Return weights for every dimension, summing to 1.

    Fixed dimensions keep their weight. Slider dimensions share the remainder
    in proportion to slider values. If every slider is at 0 they share it equally.
    """
    slider_share = 1.0 - sum(fixed_dimension_weights.values())
    if slider_share < 0:
        raise ValueError("fixed dimension weights must not exceed 1")

    total_slider_value = 0
    for slider in sliders:
        total_slider_value += slider_values.get(slider.id, slider.default)

    weights: dict[str, float] = {}
    for slider in sliders:
        if total_slider_value == 0:
            fraction = 1 / len(sliders)
        else:
            fraction = slider_values.get(slider.id, slider.default) / total_slider_value
        weights[slider.dimension] = weights.get(slider.dimension, 0.0) + slider_share * fraction

    for dimension, fixed_weight in fixed_dimension_weights.items():
        weights[dimension] = weights.get(dimension, 0.0) + fixed_weight

    rounded_weights: dict[str, float] = {}
    for dimension, weight in weights.items():
        rounded_weights[dimension] = round(weight, WEIGHT_DECIMALS)
    return rounded_weights
