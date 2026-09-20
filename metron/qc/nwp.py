"""NWP QC boundary and arrival-time leakage guard."""

from __future__ import annotations

from datetime import datetime

import numpy as np

from .boundary import bounded_qc

NWP_RANGES: dict[str, tuple[float, float]] = {
    "cape": (0.0, 20_000.0),
    "cin": (-20_000.0, 2_000.0),
    "lcl": (0.0, 20_000.0),
    "shear01": (0.0, 150.0),
    "shear06": (0.0, 150.0),
    "pwat": (0.0, 150.0),
    "frz_lvl": (0.0, 20_000.0),
    "h_m10c": (0.0, 20_000.0),
    "h_m20c": (0.0, 20_000.0),
    "dcape_proxy": (0.0, 100.0),
    "mfc850": (-1_000.0, 1_000.0),
    "conv10m": (-1_000.0, 1_000.0),
    "precip_rate": (0.0, 2_000.0),
}


def qc_nwp(
    channel: str,
    values: np.ndarray | None,
    *,
    obs_time: datetime | None,
    arrival_time: datetime | None,
    issue_time: datetime | None,
    cycle_used: str | int | None,
    shape: tuple[int, ...] | None = None,
    source: str = "gfs",
    manifest_ids: tuple[str, ...] = (),
    valid_mask: np.ndarray | None = None,
):
    """Validate an NWP field and refuse fields that arrived after issue time."""

    if channel not in NWP_RANGES:
        raise ValueError(f"unsupported NWP channel: {channel}")
    if cycle_used is None:
        return bounded_qc(
            None,
            shape=shape,
            source=source,
            obs_time=obs_time,
            arrival_time=arrival_time,
            issue_time=issue_time,
            fill_value=0.0,
            calibrated=True,
            manifest_ids=manifest_ids,
            missing_reason="nwp_cycle_unknown",
            flags={"nwp_cycle_unknown"},
            metadata={"group": "nwp", "channel": channel},
        )
    if issue_time is None or arrival_time is None or arrival_time > issue_time:
        return bounded_qc(
            None,
            shape=shape,
            source=source,
            obs_time=obs_time,
            arrival_time=arrival_time,
            issue_time=issue_time,
            fill_value=0.0,
            calibrated=True,
            manifest_ids=manifest_ids,
            missing_reason="nwp_not_arrived",
            flags={"nwp_not_arrived"},
            metadata={"group": "nwp", "channel": channel, "cycle_used": str(cycle_used)},
        )
    return bounded_qc(
        values,
        shape=shape,
        source=source,
        obs_time=obs_time,
        arrival_time=arrival_time,
        issue_time=issue_time,
        bounds=NWP_RANGES[channel],
        fill_value=0.0,
        calibrated=True,
        manifest_ids=manifest_ids,
        valid_mask=valid_mask,
        flags=set(),
        metadata={"group": "nwp", "channel": channel, "cycle_used": str(cycle_used)},
    )


qc_gfs = qc_nwp
