from datetime import datetime, timedelta, timezone

import pytest
from metron.replay import Manifest, ReplayController, ReplayError, namespace_for


def _manifest(start: datetime, source: str, offset: int) -> Manifest:
    return Manifest(
        source=source,
        object_key=f"{source}/{offset}.bin",
        obs_time=start + timedelta(seconds=offset),
        arrival_time=start + timedelta(seconds=offset),
        sha256=f"sha-{source}-{offset}",
    )


def test_replay_releases_raw_manifests_on_virtual_arrival_time() -> None:
    start = datetime(2026, 5, 3, tzinfo=timezone.utc)
    controller = ReplayController()
    state = controller.start(
        domain="pilot_e",
        t_start=start,
        t_end=start + timedelta(seconds=10),
        speed=10,
        manifests=[_manifest(start, "sat", 1), _manifest(start, "radar", 5)],
    )

    assert controller.advance(state.replay_id, 0.2)[0].source == "sat"
    assert controller.advance(state.replay_id, 0.3)[0].source == "radar"
    assert controller.get(state.replay_id).cursor == 2
    assert (
        namespace_for(state.replay_id, "products")
        in controller.get(state.replay_id).to_dict()["namespace"]["products"]
    )


def test_replay_rejects_non_raw_input_and_invalid_clock() -> None:
    start = datetime(2026, 5, 3, tzinfo=timezone.utc)
    controller = ReplayController()
    with pytest.raises(ReplayError, match="raw manifests"):
        controller.start(
            domain="pilot_e",
            t_start=start,
            t_end=start + timedelta(hours=1),
            speed=1,
            manifests=[
                {
                    "source": "products",
                    "object_key": "products/live.tif",
                    "obs_time": start,
                    "arrival_time": start,
                    "sha256": "sha",
                    "kind": "product",
                }
            ],
        )
