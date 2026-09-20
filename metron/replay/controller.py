"""Replay raw manifests on an isolated virtual clock.

Replay intentionally consumes raw manifests only.  It never reads or mutates
live grids/products, and every emitted event carries a replay namespace.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from uuid import uuid4


class ReplayError(ValueError):
    """Raised for invalid replay inputs or cross-namespace attempts."""


def _utc(value: datetime | str, name: str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReplayError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def namespace_for(replay_id: str, store: str) -> str:
    if not replay_id or "/" in replay_id or store not in {"grids", "products", "events"}:
        raise ReplayError("invalid replay namespace")
    return f"{store}/replay/{replay_id}"


@dataclass(frozen=True)
class Manifest:
    source: str
    object_key: str
    obs_time: datetime
    arrival_time: datetime
    sha256: str
    kind: str = "raw"

    def __post_init__(self) -> None:
        if not self.source.strip() or not self.object_key.strip() or not self.sha256.strip():
            raise ReplayError("manifest source, object_key, and sha256 are required")
        if self.kind != "raw":
            raise ReplayError("replay accepts raw manifests only")
        object.__setattr__(self, "obs_time", _utc(self.obs_time, "obs_time"))
        object.__setattr__(self, "arrival_time", _utc(self.arrival_time, "arrival_time"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "Manifest":
        try:
            return cls(
                source=str(value["source"]),
                object_key=str(value.get("object_key", value.get("path", ""))),
                obs_time=value["obs_time"],
                arrival_time=value["arrival_time"],
                sha256=str(value["sha256"]),
                kind=str(value.get("kind", value.get("type", "raw"))),
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, ReplayError):
                raise
            raise ReplayError(f"invalid raw manifest: {exc}") from exc


@dataclass(frozen=True)
class ReplayEvent:
    replay_id: str
    domain: str
    source: str
    object_key: str
    manifest_sha256: str
    virtual_time: datetime
    topic: str
    namespace: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "replay_id": self.replay_id,
            "domain": self.domain,
            "source": self.source,
            "object_key": self.object_key,
            "manifest_sha256": self.manifest_sha256,
            "virtual_time": _iso(self.virtual_time),
            "topic": self.topic,
            "namespace": self.namespace,
        }


@dataclass
class ReplayState:
    replay_id: str
    domain: str
    t_start: datetime
    t_end: datetime
    speed: float
    virtual_now: datetime
    manifests: tuple[Manifest, ...]
    cursor: int = 0
    status: str = "running"

    def to_dict(self) -> dict[str, Any]:
        duration = max((self.t_end - self.t_start).total_seconds(), 1.0)
        progress = min(1.0, max(0.0, (self.virtual_now - self.t_start).total_seconds() / duration))
        return {
            "replay_id": self.replay_id,
            "domain": self.domain,
            "t_start": _iso(self.t_start),
            "t_end": _iso(self.t_end),
            "speed": self.speed,
            "virtual_now": _iso(self.virtual_now),
            "progress": progress,
            "status": self.status,
            "manifest_count": len(self.manifests),
            "namespace": {
                "grids": namespace_for(self.replay_id, "grids"),
                "products": namespace_for(self.replay_id, "products"),
                "events": namespace_for(self.replay_id, "events"),
            },
        }


class ReplayController:
    def __init__(self) -> None:
        self._runs: dict[str, ReplayState] = {}

    def start(
        self,
        *,
        domain: str,
        t_start: datetime | str,
        t_end: datetime | str,
        speed: float,
        manifests: list[Manifest | Mapping[str, Any]] = (),
    ) -> ReplayState:
        if not domain.strip() or speed <= 0:
            raise ReplayError("domain and positive speed are required")
        start, end = _utc(t_start, "t_start"), _utc(t_end, "t_end")
        if start >= end:
            raise ReplayError("t_start must be before t_end")
        parsed_items: list[Manifest] = []
        for item in manifests:
            manifest = item if isinstance(item, Manifest) else Manifest.from_mapping(item)
            if start <= manifest.arrival_time <= end:
                parsed_items.append(manifest)
        parsed = tuple(sorted(parsed_items, key=lambda item: item.arrival_time))
        replay_id = uuid4().hex
        state = ReplayState(
            replay_id=replay_id,
            domain=domain,
            t_start=start,
            t_end=end,
            speed=float(speed),
            virtual_now=start,
            manifests=parsed,
        )
        self._runs[replay_id] = state
        return state

    def get(self, replay_id: str) -> ReplayState:
        try:
            return self._runs[replay_id]
        except KeyError as exc:
            raise ReplayError("replay not found") from exc

    def advance(self, replay_id: str, real_seconds: float) -> list[ReplayEvent]:
        if real_seconds < 0:
            raise ReplayError("real_seconds must be non-negative")
        state = self.get(replay_id)
        if state.status != "running":
            return []
        state.virtual_now = min(
            state.t_end,
            state.virtual_now + timedelta(seconds=real_seconds * state.speed),
        )
        events: list[ReplayEvent] = []
        while state.cursor < len(state.manifests):
            manifest = state.manifests[state.cursor]
            if manifest.arrival_time > state.virtual_now:
                break
            events.append(
                ReplayEvent(
                    replay_id=state.replay_id,
                    domain=state.domain,
                    source=manifest.source,
                    object_key=manifest.object_key,
                    manifest_sha256=manifest.sha256,
                    virtual_time=manifest.arrival_time,
                    topic=f"{namespace_for(state.replay_id, 'events')}/ingest.{manifest.source}",
                    namespace=namespace_for(state.replay_id, "events"),
                )
            )
            state.cursor += 1
        if state.virtual_now >= state.t_end:
            state.status = "completed"
        return events

    def events_until(self, replay_id: str, virtual_now: datetime | str) -> list[ReplayEvent]:
        state = self.get(replay_id)
        target = _utc(virtual_now, "virtual_now")
        if target < state.virtual_now:
            raise ReplayError("virtual clock cannot move backwards")
        return self.advance(
            replay_id,
            (target - state.virtual_now).total_seconds() / state.speed,
        )

    def delete(self, replay_id: str) -> None:
        if replay_id not in self._runs:
            raise ReplayError("replay not found")
        del self._runs[replay_id]
