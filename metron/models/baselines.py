"""Issue-time persistence and advection baselines."""

from __future__ import annotations

from typing import Iterable

import numpy as np

from .data import AvailableFrame, DataAvailabilityError, select_available_frames


def persistence(field: np.ndarray, steps: int) -> np.ndarray:
    """Repeat the last observed field for ``steps`` future bins."""
    if field.ndim != 2 or steps < 1:
        raise ValueError("field must be 2-D and steps must be positive")
    return np.repeat(field[None, ...], steps, axis=0).copy()


def advect(field: np.ndarray, motion_uv: np.ndarray, steps: int = 1) -> np.ndarray:
    """Nearest-cell semi-Lagrangian advection without periodic wraparound.

    ``motion_uv`` is ``(2, H, W)`` in grid cells per forecast step. The
    nearest-cell fallback is deterministic and intentionally bounded; a
    production pySTEPS backend can replace it without changing the contract.
    """
    if field.ndim != 2 or motion_uv.shape != (2, *field.shape) or steps < 1:
        raise ValueError("field/motion shapes or steps are invalid")
    height, width = field.shape
    y, x = np.indices(field.shape, dtype=np.float32)
    source_x = np.rint(x - motion_uv[0] * steps).astype(np.int64)
    source_y = np.rint(y - motion_uv[1] * steps).astype(np.int64)
    valid = (source_x >= 0) & (source_x < width) & (source_y >= 0) & (source_y < height)
    result = np.zeros_like(field)
    result[valid] = field[source_y[valid], source_x[valid]]
    return result


def lagrangian_persistence(field: np.ndarray, motion_uv: np.ndarray, steps: int) -> np.ndarray:
    """Repeat the last field after motion-compensated advection."""
    return np.stack([advect(field, motion_uv, step) for step in range(1, steps + 1)])


def latest_available(
    frames: Iterable[AvailableFrame], *, issue_time, count: int = 1
) -> tuple[AvailableFrame, ...]:
    """Select only frames whose manifests arrived no later than ``issue_time``."""
    try:
        return select_available_frames(frames, issue_time=issue_time, count=count)
    except DataAvailabilityError:
        raise
