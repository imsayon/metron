"""Lightning QC boundary with an explicit access gate.

ILLN access is not verified. The module therefore validates a supplied
gridded field only when the caller explicitly marks the source as verified;
otherwise it emits a missing result with ``ltg_unavailable``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Mapping

import numpy as np

from .boundary import bounded_qc


def validate_lightning_rows(rows: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    """Validate the row shape needed by a future ILLN adapter.

    This does not deduplicate or grid strokes; those remain blocked by E3-08.
    """

    required = {"time_utc", "lat", "lon", "type"}
    accepted: list[dict[str, object]] = []
    for row in rows:
        missing = required - row.keys()
        if missing:
            raise ValueError(f"lightning row missing fields: {sorted(missing)}")
        lat = float(row["lat"])
        lon = float(row["lon"])
        kind = str(row["type"])
        if not -90.0 <= lat <= 90.0 or not -180.0 <= lon <= 180.0:
            raise ValueError("lightning coordinates outside WGS84 bounds")
        if kind not in {"CG", "IC"}:
            raise ValueError(f"unsupported lightning type: {kind}")
        accepted.append(dict(row))
    return accepted


def qc_lightning(
    channel: str,
    values: np.ndarray | None,
    *,
    obs_time: datetime | None,
    arrival_time: datetime | None,
    issue_time: datetime | None,
    shape: tuple[int, ...] | None = None,
    source: str = "illn",
    manifest_ids: tuple[str, ...] = (),
    source_access_verified: bool = False,
    valid_mask: np.ndarray | None = None,
    health: int = 0,
):
    if channel not in {"dens_5", "dens_15", "dens_30", "dens_30_dew", "cg_frac"}:
        raise ValueError(f"unsupported lightning channel: {channel}")
    if not source_access_verified:
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
            missing_reason="ltg_unavailable",
            flags={"ltg_unavailable", "access_unverified"},
            metadata={"group": "ltg", "channel": channel, "health": 0},
        )
    bounds = (0.0, 1.0) if channel == "cg_frac" else (0.0, 1_000.0)
    return bounded_qc(
        values,
        shape=shape,
        source=source,
        obs_time=obs_time,
        arrival_time=arrival_time,
        issue_time=issue_time,
        bounds=bounds,
        fill_value=0.0,
        calibrated=True,
        manifest_ids=manifest_ids,
        valid_mask=valid_mask,
        missing_reason="ltg_bad_health" if health == 0 else None,
        flags={"ltg_bad_health"} if health == 0 else set(),
        metadata={"group": "ltg", "channel": channel, "health": int(health)},
    )


qc_illn = qc_lightning
