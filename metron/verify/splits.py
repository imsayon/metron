"""Verification split strategies with leakage guards."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Mapping, Sequence

from metron.common.contracts import utc

ALLOWED_SPLIT_STRATEGIES = (
    "chronological",
    "event_grouped",
    "geographic_holdout",
    "seasonal_holdout",
)


@dataclass(frozen=True, slots=True)
class VerificationFrame:
    frame_id: str
    timestamp: datetime
    event_id: str | None = None
    domain: str | None = None
    season: str | None = None
    manifest_ids: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.frame_id:
            raise ValueError("frame_id must not be empty")
        object.__setattr__(self, "timestamp", utc(self.timestamp, "timestamp"))
        object.__setattr__(self, "manifest_ids", frozenset(self.manifest_ids))


VerificationSample = VerificationFrame
SplitResult = dict[str, list[VerificationFrame]]


def _ensure_strategy(strategy: str) -> None:
    if strategy == "random_frames":
        raise ValueError("random frame splits are forbidden; use an approved split strategy")
    if strategy not in ALLOWED_SPLIT_STRATEGIES:
        choices = ", ".join(ALLOWED_SPLIT_STRATEGIES)
        raise ValueError(f"unknown split strategy {strategy!r}; choose one of {choices}")


def _parse_endpoint(value: str, *, end: bool) -> datetime:
    if len(value) == 10:
        parsed_date = date.fromisoformat(value)
        return datetime.combine(
            parsed_date + (timedelta(days=1) if end else timedelta()),
            time.min,
            tzinfo=timezone.utc,
        )
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return utc(parsed, "window endpoint")


def _parse_window(spec: str) -> tuple[datetime, datetime]:
    try:
        start, end = spec.split("/", maxsplit=1)
    except ValueError as exc:
        raise ValueError(f"window must be START/END: {spec!r}") from exc
    lower, upper = _parse_endpoint(start, end=False), _parse_endpoint(end, end=True)
    if upper <= lower:
        raise ValueError(f"window end must be after start: {spec!r}")
    return lower, upper


def _sorted(result: SplitResult) -> SplitResult:
    return {
        name: sorted(items, key=lambda item: (item.timestamp, item.frame_id))
        for name, items in result.items()
    }


def _assert_no_manifest_overlap(result: SplitResult) -> None:
    owners: dict[str, str] = {}
    for split_name, frames in result.items():
        for frame in frames:
            for manifest_id in frame.manifest_ids:
                previous = owners.setdefault(manifest_id, split_name)
                if previous != split_name:
                    raise ValueError(
                        f"manifest {manifest_id!r} appears in {previous} and {split_name}"
                    )


def chronological_split(
    records: Iterable[VerificationFrame],
    windows: Mapping[str, Sequence[str]],
    *,
    buffer_hours: int = 0,
) -> SplitResult:
    """Assign frames to non-overlapping UTC windows; boundary buffers are excluded."""

    if buffer_hours < 0:
        raise ValueError("buffer_hours must be non-negative")
    parsed: dict[str, tuple[tuple[datetime, datetime], ...]] = {
        name: tuple(
            (
                start + timedelta(hours=buffer_hours),
                end - timedelta(hours=buffer_hours),
            )
            for start, end in (_parse_window(spec) for spec in specs)
        )
        for name, specs in windows.items()
    }
    result: SplitResult = {name: [] for name in parsed}
    for frame in records:
        matches = [
            name
            for name, ranges in parsed.items()
            if any(start <= frame.timestamp < end for start, end in ranges if start < end)
        ]
        if len(matches) > 1:
            raise ValueError(f"frame {frame.frame_id!r} matches multiple chronological splits")
        if matches:
            result[matches[0]].append(frame)
    finalized = _sorted(result)
    _assert_no_manifest_overlap(finalized)
    return finalized


def _group_key(frame: VerificationFrame, group_by: str) -> str:
    if group_by == "storm_day":
        return frame.event_id or frame.timestamp.date().isoformat()
    if group_by == "event_id":
        value = frame.event_id
    else:
        value = getattr(frame, group_by, None)
    if not value:
        raise ValueError(f"frame {frame.frame_id!r} has no {group_by} group")
    return str(value)


def event_grouped_split(
    records: Iterable[VerificationFrame],
    *,
    group_by: str = "event_id",
    windows: Mapping[str, Sequence[str]] | None = None,
    assignments: Mapping[str, str] | None = None,
    train_fraction: float = 0.7,
    validation_fraction: float = 0.15,
) -> SplitResult:
    """Split whole events, never individual frames.

    Explicit ``assignments`` or chronological ``windows`` should be used for
    published runs. Fractions are only a deterministic local fallback.
    """

    if not 0 <= train_fraction <= 1 or not 0 <= validation_fraction <= 1:
        raise ValueError("split fractions must be between 0 and 1")
    if train_fraction + validation_fraction > 1:
        raise ValueError("train and validation fractions cannot exceed 1")
    grouped: dict[str, list[VerificationFrame]] = defaultdict(list)
    for frame in records:
        grouped[_group_key(frame, group_by)].append(frame)
    result: SplitResult = {"train": [], "validation": [], "test": []}

    if windows is not None:
        windowed = chronological_split(
            tuple(frame for group in grouped.values() for frame in group), windows
        )
        membership = {
            frame.frame_id: split_name
            for split_name, frames in windowed.items()
            for frame in frames
        }
        for group, frames in grouped.items():
            split_names = {
                membership[frame.frame_id] for frame in frames if frame.frame_id in membership
            }
            if len(split_names) > 1:
                raise ValueError(f"event group {group!r} straddles chronological splits")
            if split_names:
                result[split_names.pop()].extend(frames)
    elif assignments is not None:
        for group, frames in grouped.items():
            split_name = assignments.get(group)
            if split_name not in result:
                raise ValueError(f"missing or invalid split assignment for event group {group!r}")
            result[split_name].extend(frames)
    else:
        ordered_groups = sorted(
            grouped.items(),
            key=lambda item: min(frame.timestamp for frame in item[1]),
        )
        count = len(ordered_groups)
        train_count = int(count * train_fraction)
        validation_count = int(count * validation_fraction)
        if count and train_count == 0:
            train_count = 1
        for index, (_, frames) in enumerate(ordered_groups):
            if index < train_count:
                split_name = "train"
            elif index < train_count + validation_count:
                split_name = "validation"
            else:
                split_name = "test"
            result[split_name].extend(frames)

    finalized = _sorted(result)
    _assert_no_manifest_overlap(finalized)
    return finalized


def geographic_holdout_split(
    records: Iterable[VerificationFrame],
    *,
    train_domains: Sequence[str],
    test_domains: Sequence[str],
    validation_domains: Sequence[str] = (),
) -> SplitResult:
    return _domain_or_season_split(
        records,
        train_values=train_domains,
        test_values=test_domains,
        validation_values=validation_domains,
        attribute="domain",
    )


def seasonal_holdout_split(
    records: Iterable[VerificationFrame],
    *,
    train_seasons: Sequence[str],
    test_seasons: Sequence[str],
    validation_seasons: Sequence[str] = (),
) -> SplitResult:
    return _domain_or_season_split(
        records,
        train_values=train_seasons,
        test_values=test_seasons,
        validation_values=validation_seasons,
        attribute="season",
    )


def _domain_or_season_split(
    records: Iterable[VerificationFrame],
    *,
    train_values: Sequence[str],
    test_values: Sequence[str],
    validation_values: Sequence[str],
    attribute: str,
) -> SplitResult:
    buckets = {
        "train": set(train_values),
        "validation": set(validation_values),
        "test": set(test_values),
    }
    result: SplitResult = {name: [] for name in buckets}
    for frame in records:
        value = getattr(frame, attribute)
        matches = [name for name, allowed in buckets.items() if value in allowed]
        if len(matches) > 1:
            raise ValueError(f"{attribute} {value!r} is configured for multiple splits")
        if matches:
            result[matches[0]].append(frame)
    finalized = _sorted(result)
    _assert_no_manifest_overlap(finalized)
    return finalized


def split_records(
    records: Iterable[VerificationFrame], strategy: str, **kwargs: object
) -> SplitResult:
    """Dispatch only to approved split strategies."""

    _ensure_strategy(strategy)
    if strategy == "chronological":
        return chronological_split(records, **kwargs)  # type: ignore[arg-type]
    if strategy == "event_grouped":
        return event_grouped_split(records, **kwargs)  # type: ignore[arg-type]
    if strategy == "geographic_holdout":
        return geographic_holdout_split(records, **kwargs)  # type: ignore[arg-type]
    return seasonal_holdout_split(records, **kwargs)  # type: ignore[arg-type]


make_splits = split_records
