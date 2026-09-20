"""Core verification metrics with no array-framework dependency."""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Iterable, Sequence


def _values(values: Iterable[float | int]) -> tuple[float, ...]:
    result = tuple(float(value) for value in values)
    if not result:
        raise ValueError("metric inputs must not be empty")
    return result


def _same_length(
    left: Iterable[float | int],
    right: Iterable[float | int],
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    left_values, right_values = _values(left), _values(right)
    if len(left_values) != len(right_values):
        raise ValueError("metric inputs must have equal length")
    return left_values, right_values


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else math.nan


@dataclass(frozen=True, slots=True)
class ContingencyTable:
    hits: int
    false_alarms: int
    misses: int
    correct_negatives: int

    @property
    def n(self) -> int:
        return self.hits + self.false_alarms + self.misses + self.correct_negatives


def contingency_table(
    forecast: Iterable[float | int | bool],
    observed: Iterable[float | int | bool],
    *,
    threshold: float | None = None,
) -> ContingencyTable:
    forecast_values, observed_values = _same_length(forecast, observed)
    if threshold is None:
        forecast_events = tuple(bool(value) for value in forecast_values)
        observed_events = tuple(bool(value) for value in observed_values)
    else:
        forecast_events = tuple(value >= threshold for value in forecast_values)
        observed_events = tuple(value >= threshold for value in observed_values)
    hits = sum(
        predicted and actual
        for predicted, actual in zip(forecast_events, observed_events, strict=True)
    )
    false_alarms = sum(
        predicted and not actual
        for predicted, actual in zip(forecast_events, observed_events, strict=True)
    )
    misses = sum(
        not predicted and actual
        for predicted, actual in zip(forecast_events, observed_events, strict=True)
    )
    correct_negatives = sum(
        not predicted and not actual
        for predicted, actual in zip(forecast_events, observed_events, strict=True)
    )
    return ContingencyTable(hits, false_alarms, misses, correct_negatives)


def pod(table: ContingencyTable) -> float:
    return _ratio(table.hits, table.hits + table.misses)


def far(table: ContingencyTable) -> float:
    return _ratio(table.false_alarms, table.hits + table.false_alarms)


def csi(table: ContingencyTable) -> float:
    return _ratio(table.hits, table.hits + table.false_alarms + table.misses)


def bias_score(table: ContingencyTable) -> float:
    return _ratio(table.hits + table.false_alarms, table.hits + table.misses)


def equitable_threat_score(table: ContingencyTable) -> float:
    if table.n == 0:
        return math.nan
    random_hits = (table.hits + table.false_alarms) * (table.hits + table.misses) / table.n
    return _ratio(
        table.hits - random_hits,
        table.hits + table.false_alarms + table.misses - random_hits,
    )


def categorical_metrics(
    forecast: Iterable[float | int | bool],
    observed: Iterable[float | int | bool],
    *,
    threshold: float | None = None,
) -> dict[str, float]:
    table = contingency_table(forecast, observed, threshold=threshold)
    return {
        "pod": pod(table),
        "far": far(table),
        "csi": csi(table),
        "bias": bias_score(table),
        "ets": equitable_threat_score(table),
    }


def _matrix(values: Sequence[Sequence[float | int | bool]]) -> list[list[float]]:
    rows = [[float(value) for value in row] for row in values]
    if not rows or not rows[0]:
        raise ValueError("fields must not be empty")
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ValueError("fields must be rectangular")
    return rows


def _prefix_sum(field: list[list[float]]) -> list[list[float]]:
    height, width = len(field), len(field[0])
    prefix = [[0.0] * (width + 1) for _ in range(height + 1)]
    for row in range(height):
        running = 0.0
        for column in range(width):
            running += field[row][column]
            prefix[row + 1][column + 1] = prefix[row][column + 1] + running
    return prefix


def _neighbourhood_means(field: list[list[float]], scale: int) -> list[float]:
    if scale < 1 or scale > len(field) or scale > len(field[0]):
        raise ValueError("scale must fit inside both field dimensions")
    prefix = _prefix_sum(field)
    result: list[float] = []
    area = scale * scale
    for row in range(len(field) - scale + 1):
        for column in range(len(field[0]) - scale + 1):
            total = (
                prefix[row + scale][column + scale]
                - prefix[row][column + scale]
                - prefix[row + scale][column]
                + prefix[row][column]
            )
            result.append(total / area)
    return result


def fractions_skill_score(
    forecast: Sequence[Sequence[float | int | bool]],
    observed: Sequence[Sequence[float | int | bool]],
    *,
    scale: int = 1,
    threshold: float | None = None,
) -> float:
    forecast_field, observed_field = _matrix(forecast), _matrix(observed)
    if len(forecast_field) != len(observed_field) or len(forecast_field[0]) != len(
        observed_field[0]
    ):
        raise ValueError("forecast and observed fields must have equal shape")
    if threshold is not None:
        forecast_field = [[float(value >= threshold) for value in row] for row in forecast_field]
        observed_field = [[float(value >= threshold) for value in row] for row in observed_field]
    forecast_fraction = _neighbourhood_means(forecast_field, scale)
    observed_fraction = _neighbourhood_means(observed_field, scale)
    numerator = sum(
        (predicted - actual) ** 2
        for predicted, actual in zip(forecast_fraction, observed_fraction, strict=True)
    )
    denominator = sum(
        predicted**2 + actual**2
        for predicted, actual in zip(forecast_fraction, observed_fraction, strict=True)
    )
    if denominator == 0:
        return 1.0 if numerator == 0 else 0.0
    return 1.0 - numerator / denominator


def probabilistic_fss(
    probability: Sequence[Sequence[float]],
    observed: Sequence[Sequence[float | int | bool]],
    *,
    scale: int = 1,
) -> float:
    probability_field = _matrix(probability)
    if any(value < 0 or value > 1 for row in probability_field for value in row):
        raise ValueError("probabilities must be in [0, 1]")
    return fractions_skill_score(probability_field, observed, scale=scale)


def brier_score(probability: Iterable[float], observed: Iterable[float | int | bool]) -> float:
    probabilities, outcomes = _same_length(probability, observed)
    if any(value < 0 or value > 1 for value in probabilities):
        raise ValueError("probabilities must be in [0, 1]")
    return mean(
        (probability_value - outcome) ** 2
        for probability_value, outcome in zip(probabilities, outcomes, strict=True)
    )


def brier_skill_score(
    probability: Iterable[float],
    observed: Iterable[float | int | bool],
    reference: float | Iterable[float],
) -> float:
    probabilities, outcomes = _same_length(probability, observed)
    score = brier_score(probabilities, outcomes)
    if isinstance(reference, (int, float)):
        reference_score = mean((float(reference) - outcome) ** 2 for outcome in outcomes)
    else:
        reference_score = brier_score(reference, outcomes)
    return math.nan if reference_score == 0 else 1.0 - score / reference_score


@dataclass(frozen=True, slots=True)
class ReliabilityBin:
    lower: float
    upper: float
    forecast_mean: float | None
    observed_frequency: float | None
    count: int


def reliability_bins(
    probability: Iterable[float],
    observed: Iterable[float | int | bool],
    *,
    bin_count: int = 10,
) -> tuple[ReliabilityBin, ...]:
    if bin_count < 1:
        raise ValueError("bin_count must be positive")
    probabilities, outcomes = _same_length(probability, observed)
    if any(value < 0 or value > 1 for value in probabilities):
        raise ValueError("probabilities must be in [0, 1]")
    buckets: list[list[tuple[float, float]]] = [[] for _ in range(bin_count)]
    for probability_value, outcome in zip(probabilities, outcomes, strict=True):
        index = min(int(probability_value * bin_count), bin_count - 1)
        buckets[index].append((probability_value, outcome))
    return tuple(
        ReliabilityBin(
            lower=index / bin_count,
            upper=(index + 1) / bin_count,
            forecast_mean=mean(probabilities_) if probabilities_ else None,
            observed_frequency=mean(outcomes_) if outcomes_ else None,
            count=len(bucket),
        )
        for index, bucket in enumerate(buckets)
        for probabilities_, outcomes_ in [
            ([item[0] for item in bucket], [item[1] for item in bucket])
        ]
    )


def crps_ensemble(ensemble: Sequence[Sequence[float]], observed: Iterable[float]) -> float:
    observations = _values(observed)
    if len(ensemble) != len(observations) or any(not members for members in ensemble):
        raise ValueError("ensemble and observed must have equal non-empty cases")
    case_scores: list[float] = []
    for members, observation in zip(ensemble, observations, strict=True):
        values = _values(members)
        first_term = mean(abs(member - observation) for member in values)
        second_term = mean(abs(left - right) for left in values for right in values) / 2
        case_scores.append(first_term - second_term)
    return mean(case_scores)


def spread_skill_ratio(ensemble: Sequence[Sequence[float]], observed: Iterable[float]) -> float:
    observations = _values(observed)
    if len(ensemble) != len(observations) or any(not members for members in ensemble):
        raise ValueError("ensemble and observed must have equal non-empty cases")
    spreads = [pstdev(_values(members)) for members in ensemble]
    errors = [
        mean(_values(members)) - observation
        for members, observation in zip(ensemble, observations, strict=True)
    ]
    rmse_value = math.sqrt(mean(error**2 for error in errors))
    return _ratio(mean(spreads), rmse_value)


def mean_absolute_error(forecast: Iterable[float], observed: Iterable[float]) -> float:
    forecasts, observations = _same_length(forecast, observed)
    return mean(
        abs(predicted - actual) for predicted, actual in zip(forecasts, observations, strict=True)
    )


def root_mean_squared_error(forecast: Iterable[float], observed: Iterable[float]) -> float:
    forecasts, observations = _same_length(forecast, observed)
    return math.sqrt(
        mean(
            (predicted - actual) ** 2
            for predicted, actual in zip(forecasts, observations, strict=True)
        )
    )


def mean_bias(forecast: Iterable[float], observed: Iterable[float]) -> float:
    forecasts, observations = _same_length(forecast, observed)
    return mean(
        predicted - actual for predicted, actual in zip(forecasts, observations, strict=True)
    )


fss = fractions_skill_score
pfss = probabilistic_fss
brier = brier_score
bss = brier_skill_score
crps = crps_ensemble
bias = bias_score
ets = equitable_threat_score
rmse = root_mean_squared_error
mae = mean_absolute_error
