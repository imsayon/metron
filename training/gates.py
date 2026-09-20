"""Training/split gates used by model jobs."""

from __future__ import annotations

from dataclasses import dataclass


class SplitValidationError(ValueError):
    """Raised for a split that can leak adjacent frames."""


VALID_SPLITS = frozenset({"chronological", "event_grouped", "geographic_holdout", "seasonal_holdout"})


def validate_split(split: str) -> str:
    if split == "random_frames":
        raise SplitValidationError("random frame splits are forbidden")
    if split not in VALID_SPLITS:
        raise SplitValidationError(f"unknown split: {split}")
    return split
