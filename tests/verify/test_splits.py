from datetime import datetime, timezone

import pytest
from metron.verify import (
    VerificationFrame,
    chronological_split,
    event_grouped_split,
    geographic_holdout_split,
    seasonal_holdout_split,
    split_records,
)

UTC = timezone.utc


def frame(
    name: str,
    day: int,
    *,
    event: str,
    domain: str = "pilot_e",
    season: str = "pre_monsoon",
    manifest: str | None = None,
) -> VerificationFrame:
    manifests = frozenset({manifest}) if manifest else frozenset()
    return VerificationFrame(
        name,
        datetime(2026, 5, day, 12, tzinfo=UTC),
        event_id=event,
        domain=domain,
        season=season,
        manifest_ids=manifests,
    )


def test_random_frames_are_rejected() -> None:
    with pytest.raises(ValueError, match="random frame splits are forbidden"):
        split_records([], "random_frames", windows={})


def test_chronological_split_and_buffer_are_deterministic() -> None:
    records = [frame("a", 1, event="e1"), frame("b", 2, event="e2"), frame("c", 3, event="e3")]
    result = chronological_split(
        records,
        {"train": ["2026-05-01/2026-05-02"], "test": ["2026-05-03/2026-05-04"]},
    )
    assert [item.frame_id for item in result["train"]] == ["a", "b"]
    assert [item.frame_id for item in result["test"]] == ["c"]


def test_event_grouped_does_not_split_an_event() -> None:
    records = [frame("a", 1, event="e1"), frame("b", 2, event="e1"), frame("c", 3, event="e2")]
    result = event_grouped_split(records, assignments={"e1": "train", "e2": "test"})
    assert {item.event_id for item in result["train"]} == {"e1"}
    assert {item.event_id for item in result["test"]} == {"e2"}


def test_geographic_and_seasonal_holdouts() -> None:
    records = [
        frame("e", 1, event="e", domain="pilot_e"),
        frame("h", 2, event="h", domain="pilot_h", season="monsoon"),
    ]
    geographic = geographic_holdout_split(
        records,
        train_domains=["pilot_e"],
        test_domains=["pilot_h"],
    )
    seasonal = seasonal_holdout_split(
        records,
        train_seasons=["pre_monsoon"],
        test_seasons=["monsoon"],
    )
    assert [item.frame_id for item in geographic["test"]] == ["h"]
    assert [item.frame_id for item in seasonal["test"]] == ["h"]


def test_manifest_overlap_is_rejected() -> None:
    records = [
        frame("train", 1, event="e1", manifest="shared"),
        frame("test", 3, event="e2", manifest="shared"),
    ]
    with pytest.raises(ValueError, match="appears in train and test"):
        event_grouped_split(records, assignments={"e1": "train", "e2": "test"})
