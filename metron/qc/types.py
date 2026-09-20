"""Shared QC result types.

The QC boundary turns every input into a value array plus an explicit mask. A
missing or rejected input is represented by fill values and a false mask; it
is never represented by NaN in a model-facing array.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

import numpy as np


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def age_minutes(obs_time: datetime | None, issue_time: datetime | None) -> float | None:
    obs = as_utc(obs_time)
    issue = as_utc(issue_time)
    if obs is None or issue is None:
        return None
    return max(0.0, (issue - obs).total_seconds() / 60.0)


@dataclass(frozen=True)
class Provenance:
    """Source and availability facts propagated with a channel."""

    source: str
    obs_time: datetime | None = None
    arrival_time: datetime | None = None
    manifest_ids: tuple[str, ...] = ()
    calibrated: bool | None = None
    estimated_time: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "obs_time", as_utc(self.obs_time))
        object.__setattr__(self, "arrival_time", as_utc(self.arrival_time))
        object.__setattr__(self, "manifest_ids", tuple(self.manifest_ids))

    def available_at(self, issue_time: datetime | None) -> bool:
        issue = as_utc(issue_time)
        arrival = self.arrival_time
        return issue is not None and arrival is not None and arrival <= issue

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "obs_time": self.obs_time.isoformat() if self.obs_time else None,
            "arrival_time": self.arrival_time.isoformat() if self.arrival_time else None,
            "manifest_ids": list(self.manifest_ids),
            "calibrated": self.calibrated,
            "estimated_time": self.estimated_time,
            "metadata": dict(self.metadata),
        }


@dataclass
class QCResult:
    """Canonicalized channel values and the mask needed to interpret them."""

    values: np.ndarray
    valid_mask: np.ndarray
    age_min: float | None
    missing: bool
    missing_reason: str | None
    provenance: Provenance
    flags: frozenset[str] = frozenset()
    fill_value: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.values = np.asarray(self.values)
        self.valid_mask = np.asarray(self.valid_mask, dtype=np.uint8)
        if self.values.shape != self.valid_mask.shape:
            raise ValueError("values and valid_mask must have the same shape")
        if not np.isfinite(self.values.astype(np.float64, copy=False)).all():
            raise ValueError("QCResult values must contain no NaN or infinity")

    @property
    def coverage_fraction(self) -> float:
        return float(self.valid_mask.astype(bool).mean()) if self.valid_mask.size else 0.0

    @property
    def shape(self) -> tuple[int, ...]:
        return self.values.shape

    def model_values(self) -> np.ndarray:
        """Return finite values with invalid pixels replaced by the fill value."""

        return np.where(self.valid_mask.astype(bool), self.values, self.fill_value)

    def provenance_dict(self) -> dict[str, Any]:
        return {
            **self.provenance.to_dict(),
            "age_min": self.age_min,
            "missing": self.missing,
            "missing_reason": self.missing_reason,
            "flags": sorted(self.flags),
            "coverage_fraction": self.coverage_fraction,
            "metadata": dict(self.metadata),
        }


def make_qc_result(
    values: np.ndarray | None,
    *,
    shape: tuple[int, ...] | None = None,
    valid_mask: np.ndarray | None = None,
    fill_value: float = 0.0,
    age_min: float | None = None,
    missing_reason: str | None = None,
    provenance: Provenance,
    flags: set[str] | frozenset[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> QCResult:
    """Sanitize values and derive an explicit validity mask."""

    source_missing = values is None
    if values is None:
        if shape is None:
            raise ValueError("shape is required for a missing channel")
        array = np.full(shape, fill_value, dtype=np.float32)
    else:
        array = np.asarray(values)
        if shape is not None and array.shape != shape:
            raise ValueError(f"expected shape {shape}, got {array.shape}")
        if array.ndim == 0:
            array = array.reshape(1)
        if not np.issubdtype(array.dtype, np.number):
            raise TypeError("QC channel values must be numeric")
        array = array.astype(np.float32, copy=False)

    finite = np.isfinite(array)
    if source_missing:
        mask = np.zeros(array.shape, dtype=bool)
    else:
        mask = finite if valid_mask is None else np.asarray(valid_mask, dtype=bool) & finite
    if mask.shape != array.shape:
        raise ValueError("valid_mask must have the same shape as values")
    sanitized = np.where(mask, array, fill_value).astype(np.float32, copy=False)
    result_flags = set(flags or ())
    if not finite.all():
        result_flags.add("non_finite_rejected")
    if not mask.any():
        result_flags.add("no_valid_pixels")
    missing = source_missing or not bool(mask.any())
    reason = missing_reason
    if missing and reason is None:
        reason = "missing_input" if source_missing else "no_valid_pixels"
    return QCResult(
        values=sanitized,
        valid_mask=mask.astype(np.uint8),
        age_min=age_min,
        missing=missing,
        missing_reason=reason,
        provenance=provenance,
        flags=frozenset(result_flags),
        fill_value=fill_value,
        metadata=metadata or {},
    )


def missing_qc_result(
    shape: tuple[int, ...],
    *,
    source: str,
    reason: str,
    fill_value: float = 0.0,
    provenance: Provenance | None = None,
    flags: set[str] | frozenset[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> QCResult:
    return make_qc_result(
        None,
        shape=shape,
        fill_value=fill_value,
        missing_reason=reason,
        provenance=provenance or Provenance(source=source),
        flags={reason, *(flags or ())},
        metadata=metadata,
    )
