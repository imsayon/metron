"""Issue-time availability checks shared by baselines and models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import numpy as np


class DataAvailabilityError(ValueError):
    """Raised when an input was not available at the forecast issue time."""


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DataAvailabilityError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class AvailableFrame:
    values: np.ndarray
    obs_time: datetime
    arrival_time: datetime
    synthetic: bool = False

    def validate(self) -> "AvailableFrame":
        if self.values.ndim != 2 or not np.isfinite(self.values).all():
            raise DataAvailabilityError("frame must be a finite 2-D array")
        obs_time = _utc(self.obs_time)
        arrival_time = _utc(self.arrival_time)
        if arrival_time < obs_time:
            raise DataAvailabilityError("arrival_time cannot precede obs_time")
        return AvailableFrame(self.values, obs_time, arrival_time, self.synthetic)

    def usable_at(self, issue_time: datetime) -> bool:
        return self.validate().arrival_time <= _utc(issue_time)


def select_available_frames(
    frames: Iterable[AvailableFrame], *, issue_time: datetime, count: int
) -> tuple[AvailableFrame, ...]:
    if count < 1:
        raise DataAvailabilityError("count must be positive")
    usable = [frame.validate() for frame in frames if frame.usable_at(issue_time)]
    usable.sort(key=lambda frame: frame.obs_time)
    if len(usable) < count:
        raise DataAvailabilityError(
            f"need {count} frames available at issue time, found {len(usable)}"
        )
    return tuple(usable[-count:])
