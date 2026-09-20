"""M5 downburst score with no uncalibrated probability claim."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import Abstention


@dataclass(frozen=True)
class DownburstFeatures:
    divergence_norm: float
    descending_core: float
    marc_norm: float
    dcape_norm: float
    dry_midlevel: float
    has_velocity: bool


@dataclass(frozen=True)
class DownburstResult:
    raw_score: float | None
    probability: float | None
    risk_class: str | None
    abstentions: tuple[Abstention, ...] = ()
    research_only: bool = True


def downburst_score(features: DownburstFeatures) -> DownburstResult:
    if not features.has_velocity:
        return DownburstResult(
            None,
            None,
            None,
            (Abstention("M5", "no_velocity", "environment-only statement; no probability"),),
        )
    values = (
        0.35 * features.divergence_norm
        + 0.25 * features.descending_core
        + 0.15 * features.marc_norm
        + 0.15 * features.dcape_norm
        + 0.10 * features.dry_midlevel
    )
    score = max(0.0, min(1.0, values))
    risk_class = "High" if score >= 0.66 else "Moderate" if score >= 0.33 else "Low"
    return DownburstResult(score, None, risk_class)
