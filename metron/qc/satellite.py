"""Satellite input boundary.

This module deliberately stops at validation and canonicalization. The actual
INSAT readers/geolocation adapters belong to ingestion and are not invented
while source access is still being established.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np

from .boundary import bounded_qc

SATELLITE_RANGES: dict[str, tuple[float, float]] = {
    "ir1": (150.0, 400.0),
    "ir2": (150.0, 400.0),
    "wv": (150.0, 400.0),
    "mir": (150.0, 400.0),
    "vis": (0.0, 1.5),
    "swir": (0.0, 1.5),
    "d_ir1_dt": (-100.0, 100.0),
    "ir1_minus_ir2": (-100.0, 100.0),
    "wv_minus_ir1": (-200.0, 200.0),
    "ot_score": (0.0, 1.0),
}


def qc_satellite(
    channel: str,
    values: np.ndarray | None,
    *,
    obs_time: datetime | None,
    arrival_time: datetime | None,
    issue_time: datetime | None,
    shape: tuple[int, ...] | None = None,
    source: str = "insat_browse",
    calibrated: bool = False,
    manifest_ids: tuple[str, ...] = (),
    valid_mask: np.ndarray | None = None,
    estimated_time: bool = False,
):
    """Validate a satellite channel and preserve calibrated/missing flags."""

    if channel not in SATELLITE_RANGES:
        raise ValueError(f"unsupported satellite channel: {channel}")
    result = bounded_qc(
        values,
        shape=shape,
        source=source,
        obs_time=obs_time,
        arrival_time=arrival_time,
        issue_time=issue_time,
        bounds=SATELLITE_RANGES[channel],
        fill_value=0.0,
        calibrated=calibrated,
        estimated_time=estimated_time,
        manifest_ids=manifest_ids,
        valid_mask=valid_mask,
        flags={"uncalibrated"} if not calibrated else set(),
        metadata={"group": "sat", "channel": channel},
    )
    return result


qc_insat = qc_satellite
