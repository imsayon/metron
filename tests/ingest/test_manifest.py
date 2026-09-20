from datetime import datetime, timezone

from metron.ingest import ManifestRecord, ManifestStore, Observation


UTC = timezone.utc


def observation(arrival_minute: int, payload: bytes = b"fixture") -> Observation:
    obs_time = datetime(2026, 9, 21, 0, 0, tzinfo=UTC)
    return Observation(
        source="fixture_source",
        station_or_sat="fixture_station",
        payload=payload,
        obs_time=obs_time,
        arrival_time=datetime(2026, 9, 21, 0, arrival_minute, tzinfo=UTC),
        issue_time=obs_time,
        valid_time=obs_time,
    )


def test_manifest_upsert_is_idempotent_and_retains_first_arrival() -> None:
    with ManifestStore() as store:
        first = store.upsert(ManifestRecord.from_observation(observation(10), path="first.bin"))
        second = store.upsert(ManifestRecord.from_observation(observation(20), path="second.bin"))

        assert first.idempotency_key == second.idempotency_key
        assert store.count() == 1
        row = store.raw_row(first.idempotency_key)
        assert row is not None
        assert row["arrival_time"] == "2026-09-21T00:10:00Z"
        assert row["last_seen_time"] == "2026-09-21T00:20:00Z"
        assert row["seen_count"] == 2
        assert row["path"] == "second.bin"


def test_payload_change_creates_a_new_manifest() -> None:
    with ManifestStore() as store:
        store.upsert(ManifestRecord.from_observation(observation(10, b"one")))
        store.upsert(ManifestRecord.from_observation(observation(10, b"two")))

        assert store.count(source="fixture_source") == 2
