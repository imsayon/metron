"""M6 area-rate prior; trained probability is gated on genuine labels."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CloudburstResult:
    prior: float
    probability: float | None
    prior_only: bool
    research_only: bool = True


def cloudburst_prior(*, climatological_frequency: float, satellite_valid: bool) -> CloudburstResult:
    prior = max(0.0, min(1.0, float(climatological_frequency)))
    if not satellite_valid:
        return CloudburstResult(prior, None, True)
    # The prior is still not a calibrated probability until proxy/gauge labels exist.
    return CloudburstResult(prior, None, True)
