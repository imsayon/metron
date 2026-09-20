"""Radar product and volume QC boundary."""

from __future__ import annotations

from datetime import datetime

import numpy as np

from .boundary import bounded_qc

RADAR_RANGES: dict[str, tuple[float, float]] = {
    "zmax": (-32.0, 80.0),
    "z_cappi1": (-32.0, 80.0),
    "z_cappi2": (-32.0, 80.0),
    "z_m10c": (-32.0, 80.0),
    "z_m20c": (-32.0, 80.0),
    "vil": (0.0, 500.0),
    "vil_density": (0.0, 50.0),
    "mesh": (0.0, 150.0),
    "sri": (0.0, 500.0),
    "div_lowlvl": (-0.1, 0.1),
    "marc": (-100.0, 100.0),
    "vr_lowest": (-100.0, 100.0),
}

VELOCITY_CHANNELS = frozenset({"div_lowlvl", "marc", "vr_lowest"})


def qc_radar(
    channel: str,
    values: np.ndarray | None,
    *,
    obs_time: datetime | None,
    arrival_time: datetime | None,
    issue_time: datetime | None,
    shape: tuple[int, ...] | None = None,
    source: str = "imd_radar_products",
    manifest_ids: tuple[str, ...] = (),
    coverage_mask: np.ndarray | None = None,
    blocked_mask: np.ndarray | None = None,
    has_velocity: bool = False,
    estimated_time: bool = False,
):
    """Validate a radar field without fabricating volume-derived products.

    Velocity-derived channels are unavailable when no verified velocity field
    is supplied. This is the M5 boundary and is intentionally not a substitute
    for E3-07 volume processing.
    """

    if channel not in RADAR_RANGES:
        raise ValueError(f"unsupported radar channel: {channel}")
    flags: set[str] = set()
    valid_mask = coverage_mask
    reason = None
    if channel in VELOCITY_CHANNELS and not has_velocity:
        flags.add("no_velocity")
        reason = "no_velocity"
        if values is not None:
            valid_mask = np.zeros_like(np.asarray(values), dtype=bool)
    if blocked_mask is not None:
        blocked = np.asarray(blocked_mask, dtype=bool)
        valid_mask = (
            ~blocked if valid_mask is None else np.asarray(valid_mask, dtype=bool) & ~blocked
        )
        flags.add("blocked_pixels") if blocked.any() else None
    return bounded_qc(
        values,
        shape=shape,
        source=source,
        obs_time=obs_time,
        arrival_time=arrival_time,
        issue_time=issue_time,
        bounds=RADAR_RANGES[channel],
        fill_value=0.0,
        calibrated=True,
        estimated_time=estimated_time,
        manifest_ids=manifest_ids,
        valid_mask=valid_mask,
        flags=flags,
        missing_reason=reason,
        metadata={
            "group": "radar",
            "channel": channel,
            "has_velocity": bool(has_velocity),
            "source_access": "products_or_verified_volume",
        },
    )


qc_radar_field = qc_radar
