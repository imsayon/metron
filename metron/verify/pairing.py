"""Leakage-aware, deterministic forecast/truth pairing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Generic, Iterable, TypeVar

from metron.common.contracts import utc

ValueT = TypeVar("ValueT")


@dataclass(frozen=True, slots=True)
class ForecastRecord(Generic[ValueT]):
    forecast_id: str
    issue_time: datetime
    lead_min: int
    value: ValueT | None = None

    def __post_init__(self) -> None:
        if not self.forecast_id:
            raise ValueError("forecast_id must not be empty")
        if self.lead_min < 0:
            raise ValueError("lead_min must be non-negative")
        object.__setattr__(self, "issue_time", utc(self.issue_time, "issue_time"))


@dataclass(frozen=True, slots=True)
class TruthRecord(Generic[ValueT]):
    truth_id: str
    obs_time: datetime
    arrival_time: datetime
    value: ValueT | None = None

    def __post_init__(self) -> None:
        if not self.truth_id:
            raise ValueError("truth_id must not be empty")
        object.__setattr__(self, "obs_time", utc(self.obs_time, "obs_time"))
        object.__setattr__(self, "arrival_time", utc(self.arrival_time, "arrival_time"))


@dataclass(frozen=True, slots=True)
class VerificationPair(Generic[ValueT]):
    forecast: ForecastRecord[ValueT]
    truth: TruthRecord[ValueT]

    @property
    def lead_min(self) -> int:
        return self.forecast.lead_min


def pair_by_arrival_time(
    forecasts: Iterable[ForecastRecord[ValueT]],
    truths: Iterable[TruthRecord[ValueT]],
    *,
    as_of: datetime | None = None,
) -> tuple[VerificationPair[ValueT], ...]:
    """Pair each forecast to the earliest eligible truth known at ``as_of``.

    A truth event is eligible only when ``issue_time < obs_time <= issue_time + lead``.
    ``arrival_time`` is the availability boundary and deterministic tie-breaker; it
    never changes the observation window itself.
    """

    cutoff = utc(as_of, "as_of") if as_of is not None else None
    ordered_truths = tuple(truths)
    pairs: list[VerificationPair[ValueT]] = []
    ordered_forecasts = sorted(
        forecasts,
        key=lambda item: (item.issue_time, item.lead_min, item.forecast_id),
    )
    for forecast in ordered_forecasts:
        deadline = forecast.issue_time + timedelta(minutes=forecast.lead_min)
        eligible = [
            truth
            for truth in ordered_truths
            if forecast.issue_time < truth.obs_time <= deadline
            and (cutoff is None or truth.arrival_time <= cutoff)
        ]
        if eligible:
            truth = min(
                eligible,
                key=lambda item: (item.obs_time, item.arrival_time, item.truth_id),
            )
            pairs.append(VerificationPair(forecast=forecast, truth=truth))
    return tuple(pairs)


pair_forecasts = pair_by_arrival_time
