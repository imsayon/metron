"""Observation and frozen data-manifest contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .contracts import utc
from .hashing import sha256_hex, sha256_json

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class ObservationManifest:
    source: str
    station_or_sat: str
    obs_time: datetime
    arrival_time: datetime
    object_key: str
    sha256: str
    qc_status: str = "pending"
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for value, name in (
            (self.source, "source"),
            (self.station_or_sat, "station_or_sat"),
            (self.object_key, "object_key"),
            (self.qc_status, "qc_status"),
        ):
            if not value or not value.strip():
                raise ValueError(f"{name} must not be empty")
        object.__setattr__(self, "obs_time", utc(self.obs_time, "obs_time"))
        object.__setattr__(self, "arrival_time", utc(self.arrival_time, "arrival_time"))
        if not _SHA256.fullmatch(self.sha256):
            raise ValueError("sha256 must be a lowercase 64-character hexadecimal digest")
        object.__setattr__(self, "meta", dict(self.meta))

    @property
    def idempotency_key(self) -> str:
        value = "|".join(
            (
                self.source,
                self.station_or_sat,
                self.obs_time.isoformat().replace("+00:00", "Z"),
                self.sha256,
            )
        )
        return sha256_hex(value)

    @property
    def manifest_id(self) -> str:
        return self.idempotency_key

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_id": self.manifest_id,
            "source": self.source,
            "station_or_sat": self.station_or_sat,
            "obs_time": self.obs_time.isoformat().replace("+00:00", "Z"),
            "arrival_time": self.arrival_time.isoformat().replace("+00:00", "Z"),
            "object_key": self.object_key,
            "sha256": self.sha256,
            "qc_status": self.qc_status,
            "meta": dict(self.meta),
        }


@dataclass(frozen=True, slots=True)
class DataManifest:
    manifest_ids: tuple[str, ...]
    channel_version: int
    domain_version: int
    definition_version: int

    def __post_init__(self) -> None:
        ids = tuple(sorted(self.manifest_ids))
        if any(not value or not value.strip() for value in ids):
            raise ValueError("manifest_ids must contain non-empty values")
        if len(ids) != len(set(ids)):
            raise ValueError("manifest_ids must be unique")
        for value, name in (
            (self.channel_version, "channel_version"),
            (self.domain_version, "domain_version"),
            (self.definition_version, "definition_version"),
        ):
            if value < 1:
                raise ValueError(f"{name} must be positive")
        object.__setattr__(self, "manifest_ids", ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_ids": list(self.manifest_ids),
            "channel_version": self.channel_version,
            "domain_version": self.domain_version,
            "definition_version": self.definition_version,
        }

    @property
    def data_manifest_hash(self) -> str:
        return sha256_json(self.to_dict())

    @property
    def hash(self) -> str:
        return self.data_manifest_hash
