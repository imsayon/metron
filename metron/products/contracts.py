"""Provenance-first product contracts.

The implementation deliberately has no raster or database dependency.  Those
systems consume these validated contracts through the writer protocols.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any, Literal, Mapping


class ContractError(ValueError):
    """Raised when an untrusted product or provenance payload is invalid."""


Mode = Literal["live", "replay"]


def _utc(value: datetime | str, field_name: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ContractError(f"{field_name} must be ISO 8601") from exc
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ContractError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value is not None else None


def _finite(value: float, field_name: str) -> float:
    if not isfinite(value):
        raise ContractError(f"{field_name} must be finite")
    return value


@dataclass(frozen=True)
class InputProvenance:
    source: str
    obs_time: datetime | None
    age_min: float | None
    calibrated: bool | None = None
    missing: bool = False
    cycle: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source, str) or not self.source.strip():
            raise ContractError("input source is required")
        if self.obs_time is not None:
            object.__setattr__(self, "obs_time", _utc(self.obs_time, "obs_time"))
        if self.age_min is not None and (_finite(float(self.age_min), "age_min") < 0):
            raise ContractError("age_min must be non-negative")
        if self.missing and self.age_min is not None:
            raise ContractError("missing input cannot have an age")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["obs_time"] = _iso(self.obs_time)
        return data


@dataclass(frozen=True)
class Abstention:
    module: str
    reason_code: str
    detail: str | None = None
    since: datetime | None = None

    def __post_init__(self) -> None:
        if not self.module.strip() or not self.reason_code.strip():
            raise ContractError("abstention module and reason_code are required")
        if self.since is not None:
            object.__setattr__(self, "since", _utc(self.since, "abstention.since"))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["since"] = _iso(self.since)
        return data


@dataclass(frozen=True)
class Provenance:
    domain: str
    domain_version: int
    issue_time: datetime
    valid_time: datetime
    lead_min: int
    tier: str
    rung: str
    mode: Mode
    model_version: str
    inputs: tuple[InputProvenance, ...] = ()
    abstentions: tuple[Abstention, ...] = ()
    calibration_id: str | None = None
    skill_ref: str | None = None
    research: bool = False
    replay_id: str | None = None
    watermark: str = "EXPERIMENTAL GUIDANCE — NOT AN OFFICIAL IMD WARNING"

    def __post_init__(self) -> None:
        if not isinstance(self.domain, str) or not self.domain.strip() or self.domain_version < 1:
            raise ContractError("domain and positive domain_version are required")
        object.__setattr__(self, "issue_time", _utc(self.issue_time, "issue_time"))
        object.__setattr__(self, "valid_time", _utc(self.valid_time, "valid_time"))
        if self.lead_min < 0 or self.tier not in {"A", "B", "C"}:
            raise ContractError("lead_min or tier is invalid")
        if self.rung not in {"R0", "R1", "R2", "R3", "R4"}:
            raise ContractError("rung must be R0 through R4")
        if self.mode not in {"live", "replay"}:
            raise ContractError("mode must be live or replay")
        if not isinstance(self.model_version, str) or not self.model_version.strip():
            raise ContractError("model_version is required")
        if self.mode == "live" and self.replay_id is not None:
            raise ContractError("live provenance cannot have replay_id")
        if self.mode == "replay" and not self.replay_id:
            raise ContractError("replay provenance requires replay_id")
        if self.skill_ref is None and not self.research:
            raise ContractError("skill_ref is required unless research=true")
        if not isinstance(self.watermark, str) or not self.watermark.strip():
            raise ContractError("watermark is required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "domain_version": self.domain_version,
            "issue_time": _iso(self.issue_time),
            "valid_time": _iso(self.valid_time),
            "lead_min": self.lead_min,
            "tier": self.tier,
            "rung": self.rung,
            "mode": self.mode,
            "replay_id": self.replay_id,
            "model_version": self.model_version,
            "calibration_id": self.calibration_id,
            "skill_ref": self.skill_ref,
            "research": self.research,
            "inputs": [item.to_dict() for item in self.inputs],
            "abstentions": [item.to_dict() for item in self.abstentions],
            "watermark": self.watermark,
        }


@dataclass(frozen=True)
class ProductSummary:
    product: str
    variant: str
    lead_min: int
    cog_url: str
    tile_url_template: str | None
    units: str
    scale_offset: tuple[float, float]
    nodata: int | float
    stats: Mapping[str, float]
    effective_resolution_km: float | None
    colormap: str
    legend_bins: tuple[float, ...]
    provenance: Provenance

    def __post_init__(self) -> None:
        if (
            not isinstance(self.product, str)
            or not isinstance(self.variant, str)
            or not self.product.strip()
            or not self.variant.strip()
        ):
            raise ContractError("product and variant are required")
        if self.lead_min < 0 or self.lead_min != self.provenance.lead_min:
            raise ContractError("product and provenance lead_min must match")
        if (
            not isinstance(self.cog_url, str)
            or not isinstance(self.units, str)
            or not isinstance(self.colormap, str)
            or not self.cog_url.strip()
            or not self.units.strip()
            or not self.colormap.strip()
        ):
            raise ContractError("cog_url, units, and colormap are required")
        if len(self.scale_offset) != 2 or not all(isfinite(float(x)) for x in self.scale_offset):
            raise ContractError("scale_offset must contain two finite values")
        if self.effective_resolution_km is not None and self.effective_resolution_km <= 0:
            raise ContractError("effective_resolution_km must be positive")
        if any(not isfinite(float(value)) for value in self.stats.values()):
            raise ContractError("stats must contain only finite numbers")
        if any(left > right for left, right in zip(self.legend_bins, self.legend_bins[1:])):
            raise ContractError("legend_bins must be ordered")

    def to_dict(self) -> dict[str, Any]:
        return {
            "product": self.product,
            "variant": self.variant,
            "lead_min": self.lead_min,
            "cog_url": self.cog_url,
            "tile_url_template": self.tile_url_template,
            "units": self.units,
            "scale_offset": list(self.scale_offset),
            "nodata": self.nodata,
            "stats": dict(self.stats),
            "effective_resolution_km": self.effective_resolution_km,
            "colormap": self.colormap,
            "legend_bins": list(self.legend_bins),
            "provenance": self.provenance.to_dict(),
        }


@dataclass(frozen=True)
class Target:
    target_id: str
    kind: str
    name: str
    latitude: float
    longitude: float
    radius_km: float = 15.0
    admin_code: str | None = None
    is_default: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.target_id, str)
            or not isinstance(self.kind, str)
            or not isinstance(self.name, str)
            or not self.target_id.strip()
            or not self.kind.strip()
            or not self.name.strip()
        ):
            raise ContractError("target_id, kind, and name are required")
        if not -90 <= self.latitude <= 90 or not -180 <= self.longitude <= 180:
            raise ContractError("target coordinates are invalid")
        if self.radius_km <= 0 or not isfinite(float(self.radius_km)):
            raise ContractError("radius_km must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "kind": self.kind,
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "radius_km": self.radius_km,
            "admin_code": self.admin_code,
            "is_default": self.is_default,
            "geometry": {
                "type": "Point",
                "coordinates": [self.longitude, self.latitude],
            },
        }


def validate_provenance(value: Provenance | Mapping[str, Any]) -> Provenance:
    if isinstance(value, Provenance):
        return value
    try:
        inputs = tuple(
            item if isinstance(item, InputProvenance) else InputProvenance(
                source=item["source"],
                obs_time=item.get("obs_time"),
                age_min=item.get("age_min"),
                calibrated=item.get("calibrated"),
                missing=item.get("missing", False),
                cycle=item.get("cycle"),
            )
            for item in value.get("inputs", ())
        )
        abstentions = tuple(
            item if isinstance(item, Abstention) else Abstention(
                module=item["module"],
                reason_code=item["reason_code"],
                detail=item.get("detail"),
                since=item.get("since"),
            )
            for item in value.get("abstentions", ())
        )
        return Provenance(
            domain=value["domain"],
            domain_version=int(value["domain_version"]),
            issue_time=value["issue_time"],
            valid_time=value["valid_time"],
            lead_min=int(value["lead_min"]),
            tier=value["tier"],
            rung=value["rung"],
            mode=value["mode"],
            replay_id=value.get("replay_id"),
            model_version=value["model_version"],
            calibration_id=value.get("calibration_id"),
            skill_ref=value.get("skill_ref"),
            research=bool(value.get("research", False)),
            inputs=inputs,
            abstentions=abstentions,
            watermark=value.get(
                "watermark", "EXPERIMENTAL GUIDANCE — NOT AN OFFICIAL IMD WARNING"
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError(f"invalid provenance: {exc}") from exc


def validate_product_summary(value: ProductSummary | Mapping[str, Any]) -> ProductSummary:
    if isinstance(value, ProductSummary):
        return value
    try:
        scale_offset = tuple(float(item) for item in value["scale_offset"])
        return ProductSummary(
            product=value["product"],
            variant=value["variant"],
            lead_min=int(value["lead_min"]),
            cog_url=value["cog_url"],
            tile_url_template=value.get("tile_url_template"),
            units=value["units"],
            scale_offset=scale_offset,  # type: ignore[arg-type]
            nodata=value["nodata"],
            stats={key: float(item) for key, item in value.get("stats", {}).items()},
            effective_resolution_km=value.get("effective_resolution_km"),
            colormap=value["colormap"],
            legend_bins=tuple(float(item) for item in value.get("legend_bins", ())),
            provenance=validate_provenance(value["provenance"]),
        )
    except (KeyError, TypeError, ValueError, ContractError) as exc:
        if isinstance(exc, ContractError):
            raise
        raise ContractError(f"invalid product summary: {exc}") from exc


def fixture_product() -> ProductSummary:
    """Return a non-citable replay fixture, never a live operational claim."""

    issue = datetime(2026, 5, 3, 9, 30, tzinfo=timezone.utc)
    provenance = Provenance(
        domain="pilot_e",
        domain_version=1,
        issue_time=issue,
        valid_time=issue + timedelta(minutes=30),
        lead_min=30,
        tier="A",
        rung="R1",
        mode="replay",
        replay_id="fixture-day",
        model_version="fixture",
        research=True,
        inputs=(
            InputProvenance(
                source="fixture-radar",
                obs_time=issue - timedelta(minutes=10),
                age_min=10,
                calibrated=False,
            ),
        ),
    )
    return ProductSummary(
        product="ltg_prob",
        variant="p_flash_8km",
        lead_min=30,
        cog_url="replay://fixture-day/products/pilot_e/ltg_prob_L30.tif",
        tile_url_template=None,
        units="probability",
        scale_offset=(1.0 / 255.0, 0.0),
        nodata=255,
        stats={"max": 0.83, "p95": 0.41, "area_ge_0_5_km2": 1284.0},
        effective_resolution_km=8.0,
        colormap="metron_prob",
        legend_bins=(0.1, 0.3, 0.5, 0.7, 0.9),
        provenance=provenance,
    )
