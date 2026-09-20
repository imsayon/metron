"""Small deterministic resampling kernels with explicit extreme semantics."""

from __future__ import annotations

from typing import Literal

import numpy as np


Reducer = Literal["min", "max", "max_abs", "mean", "sum", "nearest", "bilinear"]


def _window(index: int, source_size: int, target_size: int) -> tuple[int, int]:
    if target_size >= source_size:
        source_index = min(source_size - 1, int(index * source_size / target_size))
        return source_index, source_index + 1
    start = int(np.floor(index * source_size / target_size))
    stop = int(np.ceil((index + 1) * source_size / target_size))
    return start, max(start + 1, stop)


def _reduce(values: np.ndarray, reducer: Reducer) -> float:
    if reducer == "min":
        return float(np.min(values))
    if reducer == "max":
        return float(np.max(values))
    if reducer == "max_abs":
        return float(values[np.argmax(np.abs(values))])
    if reducer == "sum":
        return float(np.sum(values))
    if reducer == "nearest":
        return float(values[0])
    return float(np.mean(values))


def regrid_extreme(
    values: np.ndarray,
    target_shape: tuple[int, int],
    *,
    kind: Literal["minimum", "maximum", "max_abs"],
    valid_mask: np.ndarray | None = None,
    fill_value: float = np.nan,
) -> np.ndarray:
    """Resample intensity-like fields while retaining source extrema.

    ``minimum`` is for BT-like cold minima; ``maximum`` is for dBZ/rate
    maxima. Every source cell participates in at least one target window, so
    downsampling cannot silently erase a meaningful extreme.
    """

    reducer: Reducer = {"minimum": "min", "maximum": "max", "max_abs": "max_abs"}[kind]
    return _resample(values, target_shape, reducer=reducer, valid_mask=valid_mask, fill_value=fill_value)


def _resample(
    values: np.ndarray,
    target_shape: tuple[int, int],
    *,
    reducer: Reducer,
    valid_mask: np.ndarray | None,
    fill_value: float,
) -> np.ndarray:
    source = np.asarray(values, dtype=np.float32)
    if source.ndim != 2:
        raise ValueError("regrid input must be two-dimensional")
    target_y, target_x = target_shape
    if target_y <= 0 or target_x <= 0:
        raise ValueError("target_shape must be positive")
    finite = np.isfinite(source)
    valid = finite if valid_mask is None else finite & np.asarray(valid_mask, dtype=bool)
    if valid.shape != source.shape:
        raise ValueError("valid_mask must match input shape")
    output = np.full((target_y, target_x), fill_value, dtype=np.float32)
    for ty in range(target_y):
        y0, y1 = _window(ty, source.shape[0], target_y)
        for tx in range(target_x):
            x0, x1 = _window(tx, source.shape[1], target_x)
            block = source[y0:y1, x0:x1][valid[y0:y1, x0:x1]]
            if block.size:
                output[ty, tx] = _reduce(block, reducer)
    return output


def _bilinear(values: np.ndarray, target_shape: tuple[int, int], fill_value: float) -> np.ndarray:
    source = np.asarray(values, dtype=np.float32)
    if source.ndim != 2:
        raise ValueError("regrid input must be two-dimensional")
    if np.isnan(source).any():
        # NaN-aware interpolation is a separate policy; preserve the mask by
        # using nearest-neighbour for a sparse field rather than inventing it.
        return _resample(source, target_shape, reducer="nearest", valid_mask=None, fill_value=fill_value)
    src_y = np.arange(source.shape[0], dtype=float)
    src_x = np.arange(source.shape[1], dtype=float)
    dst_y = np.linspace(0.0, source.shape[0] - 1, target_shape[0])
    dst_x = np.linspace(0.0, source.shape[1] - 1, target_shape[1])
    along_x = np.vstack([np.interp(dst_x, src_x, row) for row in source])
    return np.vstack([np.interp(dst_y, src_y, along_x[:, col]) for col in range(target_shape[1])]).T.astype(np.float32)


def regrid_channel(
    values: np.ndarray,
    target_shape: tuple[int, int],
    *,
    resampling: str,
    valid_mask: np.ndarray | None = None,
    fill_value: float = np.nan,
) -> np.ndarray:
    """Apply a channel-catalogue resampling policy."""

    policy = resampling.lower().replace("_", "-")
    if policy in {"nearest-min", "min", "minimum"}:
        return regrid_extreme(values, target_shape, kind="minimum", valid_mask=valid_mask, fill_value=fill_value)
    if policy in {"max", "maximum"}:
        return regrid_extreme(values, target_shape, kind="maximum", valid_mask=valid_mask, fill_value=fill_value)
    if policy in {"signed-max-abs", "max-abs"}:
        return regrid_extreme(values, target_shape, kind="max_abs", valid_mask=valid_mask, fill_value=fill_value)
    if policy in {"nearest"}:
        return _resample(values, target_shape, reducer="nearest", valid_mask=valid_mask, fill_value=fill_value)
    if policy in {"sum"}:
        return _resample(values, target_shape, reducer="sum", valid_mask=valid_mask, fill_value=fill_value)
    if policy in {"area-mean", "mean", "bilinear"}:
        if policy == "bilinear" and valid_mask is None:
            return _bilinear(values, target_shape, fill_value)
        return _resample(values, target_shape, reducer="mean", valid_mask=valid_mask, fill_value=fill_value)
    raise ValueError(f"unsupported resampling policy: {resampling}")
