"""Deterministic isotonic calibration with the specified fallback order."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable

import numpy as np

from .contracts import VALID_RUNGS, ContractValidationError


@dataclass(frozen=True)
class CalibrationKey:
    product: str
    lead_min: int
    rung: str
    season: str

    def without_season(self) -> "CalibrationKey":
        return CalibrationKey(self.product, self.lead_min, self.rung, "all")

    def without_rung(self) -> "CalibrationKey":
        return CalibrationKey(self.product, self.lead_min, "all", "all")

    def validate(self) -> "CalibrationKey":
        if not self.product.strip() or self.lead_min < 1 or self.rung not in (*VALID_RUNGS, "all"):
            raise ContractValidationError("invalid calibration key")
        if not self.season.strip():
            raise ContractValidationError("calibration season is required")
        return self


@dataclass(frozen=True)
class IsotonicTable:
    calibration_id: str
    key: CalibrationKey
    x: tuple[float, ...]
    y: tuple[float, ...]
    positive_count: int
    fitted_on_run_id: str
    fallback_from: CalibrationKey | None = None

    def predict(self, probabilities: Iterable[float]) -> np.ndarray:
        values = np.clip(np.asarray(tuple(probabilities), dtype=np.float64), 0, 1)
        return np.interp(values, self.x, self.y, left=self.y[0], right=self.y[-1])


def _pava(probabilities: np.ndarray, outcomes: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    order = np.argsort(probabilities, kind="mergesort")
    x = probabilities[order]
    y = outcomes[order]
    blocks: list[list[float]] = []  # [x_sum, y_sum, weight]
    for xi, yi in zip(x, y, strict=True):
        blocks.append([float(xi), float(yi), 1.0])
        while len(blocks) >= 2:
            left, right = blocks[-2], blocks[-1]
            if left[1] / left[2] <= right[1] / right[2]:
                break
            blocks[-2] = [
                left[0] + right[0],
                left[1] + right[1],
                left[2] + right[2],
            ]
            blocks.pop()
    x_out = np.asarray([block[0] / block[2] for block in blocks], dtype=np.float64)
    y_out = np.asarray([block[1] / block[2] for block in blocks], dtype=np.float64)
    x_out, unique = np.unique(x_out, return_index=True)
    return x_out, y_out[unique]


class CalibrationRegistry:
    """In-memory versioned calibration tables; persistence belongs to storage flow."""

    def __init__(self) -> None:
        self._tables: dict[CalibrationKey, IsotonicTable] = {}

    def fit(
        self,
        key: CalibrationKey,
        probabilities: Iterable[float],
        outcomes: Iterable[int | bool],
        *,
        model_version: str,
        fitted_on_run_id: str,
        min_positive: int = 2000,
        research_only: bool = False,
    ) -> IsotonicTable | None:
        key.validate()
        if research_only:
            raise ContractValidationError("research-only heads are never calibrated")
        p = np.asarray(tuple(probabilities), dtype=np.float64)
        o = np.asarray(tuple(outcomes), dtype=np.float64)
        if p.shape != o.shape or p.ndim != 1 or not len(p):
            raise ValueError("probabilities and outcomes must be non-empty 1-D arrays")
        if np.any((p < 0) | (p > 1)) or np.any((o < 0) | (o > 1)):
            raise ValueError("probabilities/outcomes must be in [0, 1]")
        positives = int(o.sum())
        selected_key = key
        fallback_from = None
        if positives < min_positive:
            for candidate in (key.without_season(), key.without_rung()):
                if candidate in self._tables:
                    selected_key = candidate
                    fallback_from = key
                    break
            else:
                return None
            return IsotonicTable(
                calibration_id=self._tables[selected_key].calibration_id,
                key=selected_key,
                x=self._tables[selected_key].x,
                y=self._tables[selected_key].y,
                positive_count=self._tables[selected_key].positive_count,
                fitted_on_run_id=self._tables[selected_key].fitted_on_run_id,
                fallback_from=fallback_from,
            )
        x, y = _pava(p, o)
        payload = {
            "model_version": model_version,
            "key": key.__dict__,
            "x": x.tolist(),
            "y": y.tolist(),
            "fitted_on_run_id": fitted_on_run_id,
        }
        calibration_id = (
            "cal-" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
        )
        table = IsotonicTable(
            calibration_id=calibration_id,
            key=key,
            x=tuple(float(value) for value in x),
            y=tuple(float(value) for value in y),
            positive_count=positives,
            fitted_on_run_id=fitted_on_run_id,
        )
        self._tables[key] = table
        return table

    def get(self, key: CalibrationKey) -> IsotonicTable | None:
        return self._tables.get(key)
