"""Small helpers shared by source-specific QC boundaries."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

import numpy as np

from .types import Provenance, age_minutes, make_qc_result, missing_qc_result


def bounded_qc(
    values: np.ndarray | None,
    *,
    shape: tuple[int, ...] | None,
    source: str,
    obs_time: datetime | None,
    arrival_time: datetime | None,
    issue_time: datetime | None,
    bounds: tuple[float, float] | None = None,
    fill_value: float = 0.0,
    calibrated: bool | None = None,
    estimated_time: bool = False,
    manifest_ids: tuple[str, ...] = (),
    valid_mask: np.ndarray | None = None,
    flags: set[str] | None = None,
    missing_reason: str | None = None,
    metadata: Mapping[str, Any] | None = None,
):
    provenance = Provenance(
        source=source,
        obs_time=obs_time,
        arrival_time=arrival_time,
        manifest_ids=manifest_ids,
        calibrated=calibrated,
        estimated_time=estimated_time,
        metadata=metadata or {},
    )
    age = age_minutes(obs_time, issue_time)
    if values is None:
        return missing_qc_result(
            shape or (),
            source=source,
            reason=missing_reason or "missing_input",
            fill_value=fill_value,
            provenance=provenance,
            flags=flags,
            metadata=metadata,
        )

    array = np.asarray(values, dtype=np.float32)
    finite = np.isfinite(array)
    accepted = finite
    result_flags = set(flags or ())
    if bounds is not None:
        low, high = bounds
        accepted &= (array >= low) & (array <= high)
        if np.any(finite & ~((array >= low) & (array <= high))):
            result_flags.add("physical_range_rejected")
    if valid_mask is not None:
        accepted &= np.asarray(valid_mask, dtype=bool)
    return make_qc_result(
        array,
        shape=shape,
        valid_mask=accepted,
        fill_value=fill_value,
        age_min=age,
        missing_reason=missing_reason,
        provenance=provenance,
        flags=result_flags,
        metadata=metadata,
    )
