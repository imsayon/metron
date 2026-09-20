"""Small, validated contracts shared by products and verification."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Mapping


class Tier(str, Enum):
    """Forecast horizon tier."""

    A = "A"
    B = "B"
    C = "C"


class Rung(str, Enum):
    """Input fallback rung, including explicit abstention."""

    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"


REASON_CODES = frozenset(
    {
        "no_radar",
        "no_velocity",
        "sat_stale",
        "sat_missing",
        "ltg_unavailable",
        "nwp_missing",
        "ood",
        "contract_violation",
        "poor_motion",
        "cycle_overrun",
        "uncalibrated_regime",
        "research_only",
    }
)


def utc(value: datetime, name: str = "time") -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware UTC")
    return value.astimezone(timezone.utc)


def _required_text(value: str, name: str) -> str:
    if not value or not value.strip():
        raise ValueError(f"{name} must not be empty")
    return value


@dataclass(frozen=True, slots=True)
class Abstention:
    module: str
    reason_code: str
    detail: str | None = None
    since: datetime | None = None

    def __post_init__(self) -> None:
        _required_text(self.module, "module")
        _required_text(self.reason_code, "reason_code")
        if self.reason_code not in REASON_CODES:
            raise ValueError(f"unknown abstention reason_code: {self.reason_code}")
        if self.since is not None:
            object.__setattr__(self, "since", utc(self.since, "since"))

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"module": self.module, "reason_code": self.reason_code}
        if self.detail is not None:
            result["detail"] = self.detail
        if self.since is not None:
            result["since"] = self.since.isoformat().replace("+00:00", "Z")
        return result


@dataclass(frozen=True, slots=True)
class InputProvenance:
    source: str
    obs_time: datetime | None = None
    age_min: float | None = None
    calibrated: bool | None = None
    missing: bool = False
    cycle: str | None = None

    def __post_init__(self) -> None:
        _required_text(self.source, "source")
        if self.obs_time is not None:
            object.__setattr__(self, "obs_time", utc(self.obs_time, "obs_time"))
        if self.age_min is not None and (not math.isfinite(self.age_min) or self.age_min < 0):
            raise ValueError("age_min must be a finite non-negative number")
        if not self.missing and self.obs_time is None and self.age_min is not None:
            raise ValueError("a non-missing input with age_min needs obs_time")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"source": self.source}
        if self.obs_time is not None:
            result["obs_time"] = self.obs_time.isoformat().replace("+00:00", "Z")
        if self.age_min is not None:
            result["age_min"] = self.age_min
        if self.calibrated is not None:
            result["calibrated"] = self.calibrated
        if self.missing:
            result["missing"] = True
        if self.cycle is not None:
            result["cycle"] = self.cycle
        return result


@dataclass(frozen=True, slots=True)
class Provenance:
    domain: str
    domain_version: int
    issue_time: datetime
    valid_time: datetime
    lead_min: int
    tier: Tier
    rung: Rung
    model_version: str
    calibration_id: str | None = None
    skill_ref: str | None = None
    mode: str = "live"
    replay_id: str | None = None
    inputs: tuple[InputProvenance, ...] = ()
    abstentions: tuple[Abstention, ...] = ()
    watermark: str = "EXPERIMENTAL GUIDANCE — NOT AN OFFICIAL IMD WARNING"
    research: bool = False

    def __post_init__(self) -> None:
        _required_text(self.domain, "domain")
        _required_text(self.model_version, "model_version")
        if self.domain_version < 1:
            raise ValueError("domain_version must be positive")
        if self.lead_min < 0:
            raise ValueError("lead_min must be non-negative")
        issue = utc(self.issue_time, "issue_time")
        valid = utc(self.valid_time, "valid_time")
        object.__setattr__(self, "issue_time", issue)
        object.__setattr__(self, "valid_time", valid)
        if valid != issue + timedelta(minutes=self.lead_min):
            raise ValueError("valid_time must equal issue_time plus lead_min")
        object.__setattr__(self, "tier", Tier(self.tier))
        object.__setattr__(self, "rung", Rung(self.rung))
        if self.mode not in {"live", "replay"}:
            raise ValueError("mode must be live or replay")
        if self.mode == "replay" and not self.replay_id:
            raise ValueError("replay mode requires replay_id")
        if self.mode == "live" and self.replay_id is not None:
            raise ValueError("live mode cannot have replay_id")
        if self.research and self.skill_ref is not None:
            raise ValueError("research products cannot carry a skill_ref")
        if not self.research and self.skill_ref is None:
            raise ValueError("non-research products require skill_ref")

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "domain_version": self.domain_version,
            "issue_time": self.issue_time.isoformat().replace("+00:00", "Z"),
            "valid_time": self.valid_time.isoformat().replace("+00:00", "Z"),
            "lead_min": self.lead_min,
            "tier": self.tier.value,
            "rung": self.rung.value,
            "mode": self.mode,
            "replay_id": self.replay_id,
            "model_version": self.model_version,
            "calibration_id": self.calibration_id,
            "skill_ref": self.skill_ref,
            "inputs": [item.to_dict() for item in self.inputs],
            "abstentions": [item.to_dict() for item in self.abstentions],
            "watermark": self.watermark,
            "research": self.research,
        }


@dataclass(frozen=True, slots=True)
class ProductSummary:
    product: str
    variant: str
    lead_min: int
    units: str
    provenance: Provenance
    stats: Mapping[str, float] = field(default_factory=dict)
    cog_url: str | None = None
    tile_url_template: str | None = None
    scale_offset: tuple[float, float] | None = None
    nodata: int | float | None = None
    effective_resolution_km: float | None = None
    colormap: str | None = None
    legend_bins: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        _required_text(self.product, "product")
        _required_text(self.variant, "variant")
        _required_text(self.units, "units")
        if self.lead_min < 0:
            raise ValueError("lead_min must be non-negative")
        if self.lead_min != self.provenance.lead_min:
            raise ValueError("product lead_min must match provenance lead_min")
        if self.effective_resolution_km is not None and self.effective_resolution_km <= 0:
            raise ValueError("effective_resolution_km must be positive")
        if any(not math.isfinite(value) for value in self.stats.values()):
            raise ValueError("stats must contain finite values")
        object.__setattr__(self, "stats", dict(self.stats))

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "product": self.product,
            "variant": self.variant,
            "lead_min": self.lead_min,
            "units": self.units,
            "stats": dict(self.stats),
            "provenance": self.provenance.to_dict(),
        }
        optional = {
            "cog_url": self.cog_url,
            "tile_url_template": self.tile_url_template,
            "scale_offset": list(self.scale_offset) if self.scale_offset is not None else None,
            "nodata": self.nodata,
            "effective_resolution_km": self.effective_resolution_km,
            "colormap": self.colormap,
            "legend_bins": list(self.legend_bins) if self.legend_bins else None,
        }
        result.update({key: value for key, value in optional.items() if value is not None})
        return result


@dataclass(frozen=True, slots=True)
class VerificationRecord:
    run_id: str
    frozen: bool
    product: str
    lead_min: int
    threshold: str
    scale_km: float | None
    region: str
    season: str
    rung: Rung
    metric: str
    value: float
    n: int
    figure_id: str
    baseline: Mapping[str, float] = field(default_factory=dict)
    ci95: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.run_id, "run_id"),
            (self.product, "product"),
            (self.threshold, "threshold"),
            (self.region, "region"),
            (self.season, "season"),
            (self.metric, "metric"),
            (self.figure_id, "figure_id"),
        ):
            _required_text(value, name)
        if self.lead_min < 0 or self.n < 0:
            raise ValueError("lead_min and n must be non-negative")
        if self.scale_km is not None and self.scale_km <= 0:
            raise ValueError("scale_km must be positive")
        if not math.isfinite(self.value):
            raise ValueError("verification value must be finite")
        object.__setattr__(self, "rung", Rung(self.rung))
        object.__setattr__(self, "baseline", dict(self.baseline))
        if self.ci95 is not None and self.ci95[0] > self.ci95[1]:
            raise ValueError("ci95 lower bound must not exceed upper bound")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "run_id": self.run_id,
            "frozen": self.frozen,
            "product": self.product,
            "lead_min": self.lead_min,
            "threshold": self.threshold,
            "scale_km": self.scale_km,
            "region": self.region,
            "season": self.season,
            "rung": self.rung.value,
            "metric": self.metric,
            "value": self.value,
            "n": self.n,
            "baseline": dict(self.baseline),
            "figure_id": self.figure_id,
        }
        if self.ci95 is not None:
            result["ci95"] = list(self.ci95)
        return result
