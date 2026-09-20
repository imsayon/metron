"""Small, explicit label curation interface with strict validation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .definitions import DEFINITION_VERSION, HAZARD_DEFINITIONS

VALID_GRADES = frozenset({"A", "B", "C"})


class LabelValidationError(ValueError):
    """Raised when a label would violate the catalogue contract."""


def _utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise LabelValidationError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class LabelEvidence:
    source: str
    locator: str
    instrument_confirmed: bool = False
    text_sha256: str | None = None
    observed_values: Mapping[str, float | str] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.source.strip() or not self.locator.strip():
            raise LabelValidationError("evidence source and locator are required")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "locator": self.locator,
            "instrument_confirmed": self.instrument_confirmed,
            "text_sha256": self.text_sha256,
            "observed_values": dict(self.observed_values),
        }


@dataclass(frozen=True)
class LabelEvent:
    event_id: str
    hazard: str
    obs_time: datetime
    latitude: float
    longitude: float
    source: str
    grade: str
    evidence: tuple[LabelEvidence, ...]
    definition_version: str = DEFINITION_VERSION
    radius_km: float = 0.0
    location_error_km: float | None = None
    time_error_min: float | None = None
    synthetic: bool = False
    proxy: bool = False

    def validate(self) -> "LabelEvent":
        if not self.event_id.strip():
            raise LabelValidationError("event_id is required")
        if self.hazard not in HAZARD_DEFINITIONS:
            raise LabelValidationError(f"unsupported hazard: {self.hazard}")
        if self.definition_version != DEFINITION_VERSION:
            raise LabelValidationError(
                f"definition_version {self.definition_version!r} != {DEFINITION_VERSION!r}"
            )
        if self.grade not in VALID_GRADES:
            raise LabelValidationError(f"grade must be one of {sorted(VALID_GRADES)}")
        obs_time = _utc(self.obs_time)
        if not -90 <= self.latitude <= 90 or not -180 <= self.longitude <= 180:
            raise LabelValidationError("latitude/longitude is outside valid bounds")
        if not self.source.strip():
            raise LabelValidationError("source is required")
        if self.radius_km < 0:
            raise LabelValidationError("radius_km cannot be negative")
        if self.location_error_km is not None and self.location_error_km < 0:
            raise LabelValidationError("location_error_km cannot be negative")
        if self.time_error_min is not None and self.time_error_min < 0:
            raise LabelValidationError("time_error_min cannot be negative")
        if not self.evidence:
            raise LabelValidationError("at least one evidence item is required")
        for item in self.evidence:
            item.validate()
        if self.grade == "A" and not any(item.instrument_confirmed for item in self.evidence):
            raise LabelValidationError("grade A requires instrument-confirmed evidence")
        if self.grade == "B":
            if self.location_error_km is None or self.location_error_km > 10:
                raise LabelValidationError("grade B requires location_error_km <= 10")
            if self.time_error_min is None or self.time_error_min > 60:
                raise LabelValidationError("grade B requires time_error_min <= 60")
        expected_proxy = HAZARD_DEFINITIONS[self.hazard].proxy
        if self.proxy != expected_proxy:
            raise LabelValidationError(f"proxy flag for {self.hazard} must be {expected_proxy}")
        return replace(self, obs_time=obs_time)

    @property
    def research_only(self) -> bool:
        return self.synthetic or self.proxy or self.grade == "C"

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "LabelEvent":
        evidence = tuple(
            item if isinstance(item, LabelEvidence) else LabelEvidence(**item)
            for item in value.get("evidence", ())
        )
        return cls(
            event_id=str(value["event_id"]),
            hazard=str(value["hazard"]),
            obs_time=_utc(value["obs_time"]),
            latitude=float(value["latitude"]),
            longitude=float(value["longitude"]),
            source=str(value["source"]),
            grade=str(value["grade"]),
            evidence=evidence,
            definition_version=str(value.get("definition_version", DEFINITION_VERSION)),
            radius_km=float(value.get("radius_km", 0.0)),
            location_error_km=(
                None
                if value.get("location_error_km") is None
                else float(value["location_error_km"])
            ),
            time_error_min=(
                None if value.get("time_error_min") is None else float(value["time_error_min"])
            ),
            synthetic=bool(value.get("synthetic", False)),
            proxy=bool(value.get("proxy", False)),
        )

    def to_mapping(self) -> dict[str, Any]:
        self.validate()
        return {
            "event_id": self.event_id,
            "hazard": self.hazard,
            "obs_time": self.obs_time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "latitude": self.latitude,
            "longitude": self.longitude,
            "source": self.source,
            "grade": self.grade,
            "evidence": [item.to_mapping() for item in self.evidence],
            "definition_version": self.definition_version,
            "radius_km": self.radius_km,
            "location_error_km": self.location_error_km,
            "time_error_min": self.time_error_min,
            "synthetic": self.synthetic,
            "proxy": self.proxy,
        }


class LabelCatalogue:
    """In-memory catalogue with JSONL persistence for human-curated rows."""

    def __init__(self, events: Iterable[LabelEvent] = ()) -> None:
        self._events: dict[str, LabelEvent] = {}
        for event in events:
            self.add(event)

    def add(self, event: LabelEvent | Mapping[str, Any]) -> LabelEvent:
        item = event if isinstance(event, LabelEvent) else LabelEvent.from_mapping(event)
        item = item.validate()
        if item.event_id in self._events:
            raise LabelValidationError(f"duplicate event_id: {item.event_id}")
        self._events[item.event_id] = item
        return item

    def grade(
        self,
        event_id: str,
        grade: str,
        *,
        location_error_km: float | None = None,
        time_error_min: float | None = None,
    ) -> LabelEvent:
        try:
            current = self._events[event_id]
        except KeyError as exc:
            raise LabelValidationError(f"unknown event_id: {event_id}") from exc
        updated = replace(
            current,
            grade=grade,
            location_error_km=location_error_km,
            time_error_min=time_error_min,
        ).validate()
        self._events[event_id] = updated
        return updated

    def validate(self) -> tuple[LabelEvent, ...]:
        return tuple(event.validate() for event in self._events.values())

    def __iter__(self):
        return iter(self._events.values())

    def __len__(self) -> int:
        return len(self._events)

    def save_jsonl(self, path: str | Path) -> None:
        rows = [json.dumps(event.to_mapping(), sort_keys=True) for event in self._events.values()]
        Path(path).write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")

    @classmethod
    def load_jsonl(cls, path: str | Path) -> "LabelCatalogue":
        catalogue = cls()
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                catalogue.add(json.loads(line))
        return catalogue
