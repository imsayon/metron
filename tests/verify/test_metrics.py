import math

import pytest
from metron.verify import (
    brier_score,
    brier_skill_score,
    contingency_table,
    crps_ensemble,
    csi,
    fractions_skill_score,
    probabilistic_fss,
    reliability_bins,
)


def test_categorical_metrics_have_analytic_perfect_values() -> None:
    table = contingency_table([1, 0, 1, 0], [1, 0, 1, 0])

    assert table.hits == 2
    assert csi(table) == 1.0


def test_fss_is_perfect_for_identical_fields_and_improves_at_neighbourhood_scale() -> None:
    observed = [[1, 0, 0], [0, 0, 0], [0, 0, 0]]
    shifted = [[0, 1, 0], [0, 0, 0], [0, 0, 0]]

    assert fractions_skill_score(observed, observed) == 1.0
    coarse = fractions_skill_score(shifted, observed, scale=2)
    fine = fractions_skill_score(shifted, observed, scale=1)
    assert coarse > fine
    assert probabilistic_fss(observed, observed) == 1.0


def test_probabilistic_metrics_have_known_values() -> None:
    assert brier_score([0.0, 1.0], [0, 1]) == 0.0
    assert brier_skill_score([0.5, 0.5], [0, 1], 0.5) == 0.0
    assert crps_ensemble([[0.0, 0.0], [1.0, 1.0]], [0.0, 1.0]) == 0.0
    assert [item.count for item in reliability_bins([0.05, 0.95], [0, 1], bin_count=2)] == [1, 1]


def test_invalid_metric_inputs_fail_loudly() -> None:
    with pytest.raises(ValueError, match="probabilities"):
        brier_score([1.1], [1])
    assert math.isnan(brier_skill_score([0.0], [0], 0.0))
