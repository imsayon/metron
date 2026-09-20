"""Observation/NWP blend with explicit missing-NWP behavior."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .contracts import Abstention


@dataclass(frozen=True)
class M3Result:
    blended: np.ndarray | None
    weights: np.ndarray | None
    abstentions: tuple[Abstention, ...] = ()
    research_only: bool = True


def blend(
    nowcast_members: np.ndarray,
    nwp_forecast: np.ndarray | None,
    *,
    observation_weight: np.ndarray | float = 0.5,
) -> M3Result:
    """Blend an ensemble mean with NWP; no NWP means no Tier B/C output."""
    if nowcast_members.ndim != 4:
        raise ValueError("nowcast_members must have shape (members, lead, y, x)")
    if nwp_forecast is None:
        return M3Result(
            blended=None,
            weights=None,
            abstentions=(Abstention("M3", "nwp_missing", "Tier B/C disabled"),),
        )
    if nwp_forecast.shape != nowcast_members.shape[1:]:
        raise ValueError("nwp_forecast shape must match (lead, y, x)")
    weights = np.asarray(observation_weight, dtype=np.float32)
    if weights.ndim == 0:
        weights = np.full((nowcast_members.shape[1],), float(weights))
    if weights.shape != (nowcast_members.shape[1],) or np.any((weights < 0) | (weights > 1)):
        raise ValueError("observation_weight must be a scalar or one value per lead in [0, 1]")
    observation = nowcast_members.mean(axis=0)
    shaped = weights[:, None, None]
    return M3Result(
        blended=shaped * observation + (1 - shaped) * nwp_forecast,
        weights=weights,
    )
