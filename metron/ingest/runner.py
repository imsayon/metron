"""Runner, quarantine sink, and source-health state for T1 ingestion."""

from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .contracts import (
    ManifestRecord,
    Observation,
    QuarantineError,
    SourceAdapter,
    SourceSpec,
    TransportError,
    sha256_bytes,
    timestamp_text,
    utc_now,
)
from .manifest import ManifestStore

UTC = timezone.utc


def _safe_part(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in value)


def _suffix(content_type: str) -> str:
    return {
        "application/json": ".json",
        "image/gif": ".gif",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "application/octet-stream": ".bin",
    }.get(content_type.split(";", 1)[0].lower(), ".bin")


class PayloadArchive:
    """Write accepted payloads outside git using deterministic content paths."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = None if root is None else Path(root)

    def save(self, observation: Observation) -> str | None:
        if self.root is None:
            return observation.path
        digest = observation.payload_sha256
        date = observation.obs_time.strftime("%Y/%m/%d")
        directory = self.root / _safe_part(observation.source) / _safe_part(observation.station_or_sat) / date
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"{digest}{_suffix(observation.content_type)}"
        if not destination.exists():
            temporary = destination.with_suffix(destination.suffix + ".tmp")
            temporary.write_bytes(observation.payload)
            temporary.replace(destination)
        return str(destination)


@dataclass(frozen=True)
class QuarantineItem:
    source: str
    reason: str
    recorded_at: datetime
    payload_sha256: str | None
    path: str | None
    details: Mapping[str, Any] = field(default_factory=dict)


class QuarantineSink:
    """Persist diagnostics and, when configured, the rejected payload itself."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = None if root is None else Path(root)

    def record(
        self,
        source: str,
        error: QuarantineError,
        *,
        recorded_at: datetime,
    ) -> QuarantineItem:
        payload_hash = sha256_bytes(error.payload) if error.payload else None
        payload_path: Path | None = None
        metadata_path: Path | None = None
        if self.root is not None:
            directory = self.root / _safe_part(source)
            directory.mkdir(parents=True, exist_ok=True)
            stem = f"{recorded_at.strftime('%Y%m%dT%H%M%SZ')}-{payload_hash or 'no-payload'}"
            if error.payload:
                payload_path = directory / f"{stem}.bin"
                if not payload_path.exists():
                    payload_path.write_bytes(error.payload)
            metadata_path = directory / f"{stem}.json"
            metadata = {
                "source": source,
                "reason": error.reason,
                "url": error.url,
                "recorded_at": timestamp_text(recorded_at),
                "payload_sha256": payload_hash,
                "payload_path": str(payload_path) if payload_path else None,
                "details": dict(error.details),
            }
            metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return QuarantineItem(
            source=source,
            reason=error.reason,
            recorded_at=recorded_at,
            payload_sha256=payload_hash,
            path=str(metadata_path) if metadata_path else None,
            details={"url": error.url, **error.details},
        )


@dataclass(frozen=True)
class HealthSnapshot:
    source: str
    status: str
    publishing: bool
    attempts: int
    accepted: int
    quarantined: int
    failures: int
    consecutive_failures: int
    last_attempt: datetime | None
    last_success: datetime | None
    last_failure: datetime | None
    last_observation: datetime | None
    last_error: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "status": self.status,
            "publishing": self.publishing,
            "attempts": self.attempts,
            "accepted": self.accepted,
            "quarantined": self.quarantined,
            "failures": self.failures,
            "consecutive_failures": self.consecutive_failures,
            "last_attempt": None if self.last_attempt is None else timestamp_text(self.last_attempt),
            "last_success": None if self.last_success is None else timestamp_text(self.last_success),
            "last_failure": None if self.last_failure is None else timestamp_text(self.last_failure),
            "last_observation": None
            if self.last_observation is None
            else timestamp_text(self.last_observation),
            "last_error": self.last_error,
        }


class SourceHealth:
    def __init__(self, spec: SourceSpec) -> None:
        self.spec = spec
        self.attempts = 0
        self.accepted = 0
        self.quarantined = 0
        self.failures = 0
        self.consecutive_failures = 0
        self.last_attempt: datetime | None = None
        self.last_success: datetime | None = None
        self.last_failure: datetime | None = None
        self.last_observation: datetime | None = None
        self.last_error: str | None = None

    def attempt(self, at: datetime) -> None:
        self.attempts += 1
        self.last_attempt = at.astimezone(UTC)

    def success(self, observation: Observation) -> None:
        self.accepted += 1
        self.consecutive_failures = 0
        self.last_success = observation.arrival_time
        self.last_observation = observation.obs_time
        self.last_error = None

    def quarantine(self, error: QuarantineError, at: datetime) -> None:
        self.quarantined += 1
        self.last_error = error.reason

    def failure(self, error: Exception, at: datetime) -> None:
        self.failures += 1
        self.consecutive_failures += 1
        self.last_failure = at.astimezone(UTC)
        self.last_error = f"{type(error).__name__}: {error}"

    def snapshot(self, now: datetime | None = None) -> HealthSnapshot:
        current = (now or utc_now()).astimezone(UTC)
        if self.last_success is None:
            status = "failed" if self.last_failure is not None else "unknown"
            publishing = False
        else:
            age = current - self.last_success
            healthy_window = timedelta(seconds=self.spec.expected_latency_s + self.spec.cadence_s)
            grace_window = timedelta(seconds=max(self.spec.cadence_s * 3, self.spec.expected_latency_s * 2))
            if age <= healthy_window and self.consecutive_failures == 0:
                status = "healthy"
            elif age <= grace_window:
                status = "degraded"
            else:
                status = "stale"
            publishing = age <= grace_window
        return HealthSnapshot(
            source=self.spec.name,
            status=status,
            publishing=publishing,
            attempts=self.attempts,
            accepted=self.accepted,
            quarantined=self.quarantined,
            failures=self.failures,
            consecutive_failures=self.consecutive_failures,
            last_attempt=self.last_attempt,
            last_success=self.last_success,
            last_failure=self.last_failure,
            last_observation=self.last_observation,
            last_error=self.last_error,
        )


class SourceHealthRegistry:
    def __init__(self) -> None:
        self._states: dict[str, SourceHealth] = {}

    def for_spec(self, spec: SourceSpec) -> SourceHealth:
        state = self._states.get(spec.name)
        if state is None:
            state = SourceHealth(spec)
            self._states[spec.name] = state
        return state

    def snapshots(self, now: datetime | None = None) -> dict[str, HealthSnapshot]:
        return {name: state.snapshot(now) for name, state in self._states.items()}


@dataclass(frozen=True)
class IngestResult:
    source: str
    manifests: tuple[ManifestRecord, ...]
    quarantined: tuple[QuarantineItem, ...]
    errors: tuple[str, ...]
    health: HealthSnapshot

    @property
    def accepted_count(self) -> int:
        return len(self.manifests)


class IngestRunner:
    """Run one source poll and make accepted writes idempotent."""

    def __init__(
        self,
        manifests: ManifestStore,
        *,
        archive_root: str | Path | None = None,
        quarantine_root: str | Path | None = None,
        health: SourceHealthRegistry | None = None,
        clock: Any = utc_now,
        raise_errors: bool = False,
    ) -> None:
        self.manifests = manifests
        self.archive = PayloadArchive(archive_root)
        self.quarantine = QuarantineSink(quarantine_root)
        self.health = health or SourceHealthRegistry()
        self.clock = clock
        self.raise_errors = raise_errors

    def run_once(self, adapter: SourceAdapter, now: datetime | None = None) -> IngestResult:
        spec = adapter.spec
        state = self.health.for_spec(spec)
        attempted_at = (now or self.clock()).astimezone(UTC)
        state.attempt(attempted_at)
        accepted: list[ManifestRecord] = []
        quarantined: list[QuarantineItem] = []
        errors: list[str] = []
        try:
            observations = adapter.poll(attempted_at)
            for observation in observations:
                try:
                    observation.validate()
                    path = self.archive.save(observation)
                    record = self.manifests.upsert(
                        ManifestRecord.from_observation(observation, path=path)
                    )
                    accepted.append(record)
                    state.success(observation)
                except QuarantineError as error:
                    item = self.quarantine.record(spec.name, error, recorded_at=self.clock().astimezone(UTC))
                    quarantined.append(item)
                    state.quarantine(error, item.recorded_at)
                except (ValueError, TypeError) as error:
                    wrapped = QuarantineError(
                        "invalid_observation",
                        payload=observation.payload,
                        details={"error": str(error)},
                    )
                    item = self.quarantine.record(spec.name, wrapped, recorded_at=self.clock().astimezone(UTC))
                    quarantined.append(item)
                    state.quarantine(wrapped, item.recorded_at)
        except QuarantineError as error:
            item = self.quarantine.record(spec.name, error, recorded_at=self.clock().astimezone(UTC))
            quarantined.append(item)
            state.quarantine(error, item.recorded_at)
        except Exception as error:  # transport and adapter bugs are visible in the result
            state.failure(error, self.clock())
            errors.append(f"{type(error).__name__}: {error}")
            if self.raise_errors:
                raise
        return IngestResult(
            source=spec.name,
            manifests=tuple(accepted),
            quarantined=tuple(quarantined),
            errors=tuple(errors),
            health=state.snapshot(self.clock()),
        )

    def health_snapshot(self, source: str, now: datetime | None = None) -> HealthSnapshot | None:
        state = self.health._states.get(source)
        return None if state is None else state.snapshot(now)
