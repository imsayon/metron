from datetime import datetime, timezone

from metron.common import DataManifest, ObservationManifest

UTC = timezone.utc


def observation(source: str = "radar") -> ObservationManifest:
    return ObservationManifest(
        source=source,
        station_or_sat="kolkata",
        obs_time=datetime(2026, 5, 3, 9, 30, tzinfo=UTC),
        arrival_time=datetime(2026, 5, 3, 9, 35, tzinfo=UTC),
        object_key="radar/2026/05/03/frame.gif",
        sha256="a" * 64,
    )


def test_manifest_id_is_content_and_order_stable() -> None:
    first = observation()
    second = observation("satellite")
    left = DataManifest((second.manifest_id, first.manifest_id), 1, 1, 1)
    right = DataManifest((first.manifest_id, second.manifest_id), 1, 1, 1)

    assert first.manifest_id == first.idempotency_key
    assert left.data_manifest_hash == right.data_manifest_hash


def test_manifest_hash_changes_with_contract_version() -> None:
    item = observation()
    first = DataManifest((item.manifest_id,), 1, 1, 1)
    second = DataManifest((item.manifest_id,), 2, 1, 1)
    assert first.hash != second.hash


def test_manifest_availability_uses_arrival_time() -> None:
    item = observation()

    assert not item.available_at(datetime(2026, 5, 3, 9, 34, tzinfo=UTC))
    assert item.available_at(datetime(2026, 5, 3, 9, 35, tzinfo=UTC))
