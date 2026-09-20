"""Mask, age, and provenance propagation across channels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from metron.qc.types import QCResult


@dataclass(frozen=True)
class MaskBundle:
    valid: Mapping[str, np.ndarray]
    age_min: Mapping[str, np.ndarray]
    missing: Mapping[str, bool]
    reasons: Mapping[str, str | None]
    manifest_ids: tuple[str, ...]


def propagate_masks(
    results: Mapping[str, QCResult], *, shape: tuple[int, int] | None = None
) -> MaskBundle:
    valid: dict[str, np.ndarray] = {}
    ages: dict[str, np.ndarray] = {}
    missing: dict[str, bool] = {}
    reasons: dict[str, str | None] = {}
    manifests: list[str] = []
    for name, result in results.items():
        if shape is not None and result.shape != shape:
            raise ValueError(f"{name} has shape {result.shape}, expected {shape}")
        valid[name] = result.valid_mask.astype(np.uint8, copy=True)
        age = 120.0 if result.age_min is None else float(result.age_min)
        ages[name] = np.full(result.shape, min(120.0, max(0.0, age)), dtype=np.float32)
        missing[name] = result.missing
        reasons[name] = result.missing_reason
        manifests.extend(result.provenance.manifest_ids)
    return MaskBundle(
        valid=valid,
        age_min=ages,
        missing=missing,
        reasons=reasons,
        manifest_ids=tuple(dict.fromkeys(manifests)),
    )


def combined_valid_mask(results: Mapping[str, QCResult], names: Sequence[str]) -> np.ndarray:
    if not names:
        raise ValueError("at least one channel is required")
    try:
        masks = [results[name].valid_mask.astype(bool) for name in names]
    except KeyError as exc:
        raise KeyError(f"missing channel for mask combination: {exc.args[0]}") from exc
    return np.logical_and.reduce(masks).astype(np.uint8)
