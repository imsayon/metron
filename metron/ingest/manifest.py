"""SQLite-backed manifest store for idempotent ingestion."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from .contracts import ManifestRecord, parse_timestamp, timestamp_text


SCHEMA = """
CREATE TABLE IF NOT EXISTS obs_manifest (
    idempotency_key TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    station_or_sat TEXT NOT NULL,
    obs_time TEXT NOT NULL,
    arrival_time TEXT NOT NULL,
    issue_time TEXT NOT NULL,
    valid_time TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    payload_size INTEGER NOT NULL,
    path TEXT,
    content_type TEXT NOT NULL,
    status TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    first_seen_time TEXT NOT NULL,
    last_seen_time TEXT NOT NULL,
    seen_count INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_obs_manifest_source_obs
    ON obs_manifest(source, station_or_sat, obs_time);
CREATE INDEX IF NOT EXISTS idx_obs_manifest_arrival
    ON obs_manifest(arrival_time);
"""


class ManifestStore:
    """Store manifests only; payload bytes remain in the runner's archive sink."""

    def __init__(self, database: str | Path = ":memory:") -> None:
        self.database = str(database)
        self.connection = sqlite3.connect(self.database)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "ManifestStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def upsert(self, record: ManifestRecord) -> ManifestRecord:
        """Insert once, then refresh mutable arrival/path/status metadata.

        The first arrival is retained for latency accounting. Re-fetches update
        ``last_seen_time`` and ``seen_count`` without creating another manifest.
        """

        now = timestamp_text(record.arrival_time)
        metadata_json = json.dumps(dict(record.metadata), sort_keys=True, separators=(",", ":"))
        self.connection.execute(
            """
            INSERT INTO obs_manifest (
                idempotency_key, source, station_or_sat, obs_time, arrival_time,
                issue_time, valid_time, payload_sha256, payload_size, path,
                content_type, status, metadata_json, first_seen_time, last_seen_time,
                seen_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(idempotency_key) DO UPDATE SET
                path = COALESCE(excluded.path, obs_manifest.path),
                status = excluded.status,
                metadata_json = excluded.metadata_json,
                last_seen_time = excluded.last_seen_time,
                seen_count = obs_manifest.seen_count + 1
            """,
            (
                record.idempotency_key,
                record.source,
                record.station_or_sat,
                timestamp_text(record.obs_time),
                timestamp_text(record.arrival_time),
                timestamp_text(record.issue_time),
                timestamp_text(record.valid_time),
                record.payload_sha256,
                record.payload_size,
                record.path,
                record.content_type,
                record.status,
                metadata_json,
                now,
                now,
                1,
            ),
        )
        self.connection.commit()
        stored = self.get(record.idempotency_key)
        if stored is None:  # pragma: no cover - defensive SQLite failure guard
            raise RuntimeError(f"manifest upsert did not persist {record.idempotency_key}")
        return stored

    def get(self, idempotency_key: str) -> ManifestRecord | None:
        row = self.connection.execute(
            "SELECT * FROM obs_manifest WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        return None if row is None else self._record(row)

    def count(self, *, source: str | None = None) -> int:
        if source is None:
            row = self.connection.execute("SELECT COUNT(*) AS n FROM obs_manifest").fetchone()
        else:
            row = self.connection.execute(
                "SELECT COUNT(*) AS n FROM obs_manifest WHERE source = ?", (source,)
            ).fetchone()
        return int(row["n"])

    def list(
        self,
        *,
        source: str | None = None,
        station_or_sat: str | None = None,
        limit: int | None = None,
    ) -> list[ManifestRecord]:
        clauses: list[str] = []
        values: list[Any] = []
        if source is not None:
            clauses.append("source = ?")
            values.append(source)
        if station_or_sat is not None:
            clauses.append("station_or_sat = ?")
            values.append(station_or_sat)
        query = "SELECT * FROM obs_manifest"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY obs_time, source, station_or_sat"
        if limit is not None:
            if limit < 0:
                raise ValueError("limit must not be negative")
            query += " LIMIT ?"
            values.append(limit)
        return [self._record(row) for row in self.connection.execute(query, values)]

    def _record(self, row: sqlite3.Row) -> ManifestRecord:
        return ManifestRecord(
            idempotency_key=row["idempotency_key"],
            source=row["source"],
            station_or_sat=row["station_or_sat"],
            obs_time=parse_timestamp(row["obs_time"]),
            arrival_time=parse_timestamp(row["arrival_time"]),
            issue_time=parse_timestamp(row["issue_time"]),
            valid_time=parse_timestamp(row["valid_time"]),
            payload_sha256=row["payload_sha256"],
            payload_size=int(row["payload_size"]),
            path=row["path"],
            content_type=row["content_type"],
            status=row["status"],
            metadata=json.loads(row["metadata_json"]),
        )

    def raw_row(self, idempotency_key: str) -> Mapping[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM obs_manifest WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        return None if row is None else dict(row)
