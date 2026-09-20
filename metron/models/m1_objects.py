"""Deterministic storm objects, tracking, lineage, and arrival windows."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterable

import numpy as np

from .baselines import advect

try:  # scipy is optional for the small fallback package
    from scipy.optimize import linear_sum_assignment
except ImportError:  # pragma: no cover - exercised only in minimal runtimes
    linear_sum_assignment = None


@dataclass(frozen=True)
class StormDetection:
    footprint: np.ndarray
    centroid: tuple[float, float]  # x, y in grid cells
    area_cells: int
    max_value: float
    bbox: tuple[int, int, int, int]  # xmin, ymin, xmax, ymax


def detect_objects(
    field: np.ndarray, *, threshold: float, min_area: int = 8
) -> tuple[StormDetection, ...]:
    """Find 8-connected threshold exceedances on one grid frame."""
    if field.ndim != 2 or min_area < 1:
        raise ValueError("field must be 2-D and min_area must be positive")
    active = np.asarray(field >= threshold, dtype=bool)
    visited = np.zeros_like(active, dtype=bool)
    height, width = active.shape
    detections: list[StormDetection] = []
    for y0 in range(height):
        for x0 in range(width):
            if not active[y0, x0] or visited[y0, x0]:
                continue
            queue = deque([(y0, x0)])
            visited[y0, x0] = True
            cells: list[tuple[int, int]] = []
            while queue:
                y, x = queue.popleft()
                cells.append((y, x))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if not dx and not dy:
                            continue
                        ny, nx = y + dy, x + dx
                        if (
                            0 <= ny < height
                            and 0 <= nx < width
                            and active[ny, nx]
                            and not visited[ny, nx]
                        ):
                            visited[ny, nx] = True
                            queue.append((ny, nx))
            if len(cells) < min_area:
                continue
            ys = np.fromiter((item[0] for item in cells), dtype=np.int64)
            xs = np.fromiter((item[1] for item in cells), dtype=np.int64)
            footprint = np.zeros_like(active)
            footprint[ys, xs] = True
            detections.append(
                StormDetection(
                    footprint=footprint,
                    centroid=(float(xs.mean()), float(ys.mean())),
                    area_cells=len(cells),
                    max_value=float(field[ys, xs].max()),
                    bbox=(int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())),
                )
            )
    return tuple(detections)


@dataclass(frozen=True)
class StormObject:
    track_id: str
    footprint: np.ndarray
    centroid: tuple[float, float]
    area_cells: int
    max_value: float
    lifecycle_state: str
    age_frames: int
    missed_frames: int = 0
    parent_track_ids: tuple[str, ...] = ()
    child_track_ids: tuple[str, ...] = ()

    def to_mapping(self) -> dict[str, object]:
        return {
            "track_id": self.track_id,
            "centroid": self.centroid,
            "area_cells": self.area_cells,
            "max_value": self.max_value,
            "lifecycle_state": self.lifecycle_state,
            "age_frames": self.age_frames,
            "missed_frames": self.missed_frames,
            "parent_track_ids": self.parent_track_ids,
            "child_track_ids": self.child_track_ids,
        }


@dataclass
class _TrackState:
    object: StormObject
    previous_max: float
    previous_area: int


def _greedy_assignment(cost: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    pairs: list[tuple[int, int]] = []
    used_rows: set[int] = set()
    used_cols: set[int] = set()
    for flat_index in np.argsort(cost, axis=None):
        row, col = np.unravel_index(flat_index, cost.shape)
        if row not in used_rows and col not in used_cols:
            used_rows.add(int(row))
            used_cols.add(int(col))
            pairs.append((int(row), int(col)))
    if not pairs:
        return np.array([], dtype=int), np.array([], dtype=int)
    rows, cols = zip(*pairs, strict=True)
    return np.asarray(rows), np.asarray(cols)


class StormTracker:
    """Hungarian/advection tracker with explicit split and merge parents."""

    def __init__(self, *, km_per_cell: float = 2.0, gate_km: float = 30.0) -> None:
        if km_per_cell <= 0 or gate_km <= 0:
            raise ValueError("km_per_cell and gate_km must be positive")
        self.km_per_cell = km_per_cell
        self.gate_km = gate_km
        self._active: dict[str, _TrackState] = {}
        self._next_id = 1
        self._history: list[StormObject] = []
        self._lineage: list[tuple[str, str, str]] = []

    @property
    def history(self) -> tuple[StormObject, ...]:
        return tuple(self._history)

    @property
    def lineage(self) -> tuple[tuple[str, str, str], ...]:
        return tuple(self._lineage)

    def _new_id(self) -> str:
        value = f"T{self._next_id:06d}"
        self._next_id += 1
        return value

    def _predicted_centroid(
        self, state: _TrackState, motion_uv: np.ndarray | None
    ) -> tuple[float, float]:
        x, y = state.object.centroid
        if motion_uv is None:
            return x, y
        if motion_uv.shape != (2, *state.object.footprint.shape):
            raise ValueError("motion_uv shape must match detection grid")
        ix = min(max(int(round(x)), 0), motion_uv.shape[2] - 1)
        iy = min(max(int(round(y)), 0), motion_uv.shape[1] - 1)
        return x + float(motion_uv[0, iy, ix]), y + float(motion_uv[1, iy, ix])

    def update(
        self,
        detections: Iterable[StormDetection],
        *,
        motion_uv: np.ndarray | None = None,
    ) -> tuple[StormObject, ...]:
        current = tuple(detections)
        previous = tuple(self._active.values())
        assigned: dict[int, int] = {}
        if previous and current:
            cost = np.empty((len(previous), len(current)), dtype=np.float64)
            distances = np.empty_like(cost)
            for row, state in enumerate(previous):
                px, py = self._predicted_centroid(state, motion_uv)
                for col, detection in enumerate(current):
                    distance = np.hypot(px - detection.centroid[0], py - detection.centroid[1])
                    distances[row, col] = distance * self.km_per_cell
                    cost[row, col] = (
                        distances[row, col] / self.gate_km
                        + 0.5
                        * abs(np.log((detection.area_cells + 1) / (state.object.area_cells + 1)))
                        + 0.3 * abs(detection.max_value - state.previous_max) / 10
                    )
            if linear_sum_assignment is not None:
                rows, cols = linear_sum_assignment(cost)
            else:  # pragma: no cover - scipy is present in the test runtime
                rows, cols = _greedy_assignment(cost)
            for row, col in zip(rows, cols, strict=True):
                if distances[row, col] <= self.gate_km:
                    assigned[int(col)] = int(row)

        overlap_parents: dict[int, list[str]] = {index: [] for index in range(len(current))}
        for col, detection in enumerate(current):
            for state in previous:
                if np.logical_and(state.object.footprint, detection.footprint).any():
                    overlap_parents[col].append(state.object.track_id)

        next_active: dict[str, _TrackState] = {}
        output: list[StormObject] = []
        for col, detection in enumerate(current):
            matched_state = previous[assigned[col]] if col in assigned else None
            parents = set(overlap_parents[col])
            if matched_state is not None:
                parents.add(matched_state.object.track_id)
                track_id = matched_state.object.track_id
                age = matched_state.object.age_frames + 1
                previous_max = matched_state.previous_max
                previous_area = matched_state.previous_area
            else:
                track_id = self._new_id()
                age = 1
                previous_max = detection.max_value
                previous_area = detection.area_cells
            if age == 1:
                state_name = "Candidate"
            elif detection.max_value >= 45:
                state_name = "Mature"
            elif (
                matched_state is not None
                and detection.max_value <= previous_max - 5
                and detection.area_cells < previous_area
            ):
                state_name = "Decaying"
            else:
                state_name = "Developing"
            item = StormObject(
                track_id=track_id,
                footprint=detection.footprint.copy(),
                centroid=detection.centroid,
                area_cells=detection.area_cells,
                max_value=detection.max_value,
                lifecycle_state=state_name,
                age_frames=age,
                parent_track_ids=tuple(sorted(parent for parent in parents if parent != track_id)),
            )
            output.append(item)
            next_active[track_id] = _TrackState(item, detection.max_value, detection.area_cells)
            self._history.append(item)
            for parent_id in item.parent_track_ids:
                if parent_id != track_id:
                    self._lineage.append((parent_id, track_id, "split_or_merge"))

        for row, state in enumerate(previous):
            if row in assigned.values():
                continue
            missed = state.object.missed_frames + 1
            if missed >= 2:
                dissipated = StormObject(
                    track_id=state.object.track_id,
                    footprint=state.object.footprint,
                    centroid=state.object.centroid,
                    area_cells=state.object.area_cells,
                    max_value=state.object.max_value,
                    lifecycle_state="Dissipated",
                    age_frames=state.object.age_frames,
                    missed_frames=missed,
                    parent_track_ids=state.object.parent_track_ids,
                    child_track_ids=state.object.child_track_ids,
                )
                self._history.append(dissipated)
            else:
                next_active[state.object.track_id] = _TrackState(
                    StormObject(
                        track_id=state.object.track_id,
                        footprint=state.object.footprint,
                        centroid=state.object.centroid,
                        area_cells=state.object.area_cells,
                        max_value=state.object.max_value,
                        lifecycle_state="Decaying",
                        age_frames=state.object.age_frames,
                        missed_frames=missed,
                        parent_track_ids=state.object.parent_track_ids,
                        child_track_ids=state.object.child_track_ids,
                    ),
                    state.previous_max,
                    state.previous_area,
                )
        self._active = next_active
        return tuple(output)


@dataclass(frozen=True)
class Target:
    target_id: str
    x: float
    y: float
    radius_km: float


@dataclass(frozen=True)
class ArrivalWindow:
    track_id: str
    target_id: str
    p_arrival: float
    t10: int | None
    t50: int | None
    t90: int | None
    p_decay: float
    radius_km: float


@dataclass(frozen=True)
class EmpiricalSurvival:
    durations_min: tuple[float, ...]

    @classmethod
    def fit(cls, durations_min: Iterable[float]) -> "EmpiricalSurvival":
        values = tuple(sorted(float(value) for value in durations_min if value > 0))
        if not values:
            raise ValueError("at least one positive track duration is required")
        return cls(values)

    def decay_probability(self, *, age_min: float, lead_min: float) -> float:
        cutoff = age_min + lead_min
        return float(sum(value <= cutoff for value in self.durations_min) / len(self.durations_min))


def _arrival_for_member(
    footprint: np.ndarray,
    target: Target,
    motion_uv: np.ndarray,
    *,
    horizon_steps: int,
    step_minutes: int,
    km_per_cell: float,
) -> int | None:
    if motion_uv.shape != (2, *footprint.shape):
        raise ValueError("member motion shape must match object footprint")
    moving = footprint.astype(np.float32)
    radius_cells = target.radius_km / km_per_cell
    yy, xx = np.indices(footprint.shape)
    for step in range(1, horizon_steps + 1):
        moving = advect(moving, motion_uv, 1)
        hit = moving > 0.5
        if (
            hit.any()
            and np.min((xx[hit] - target.x) ** 2 + (yy[hit] - target.y) ** 2) <= radius_cells**2
        ):
            return step * step_minutes
    return None


def compute_arrival_windows(
    storm: StormObject,
    targets: Iterable[Target],
    motion_members: np.ndarray,
    *,
    horizon_steps: int = 36,
    step_minutes: int = 10,
    km_per_cell: float = 2.0,
    survival: EmpiricalSurvival | None = None,
) -> tuple[ArrivalWindow, ...]:
    """Compute P(arrival), P10/P50/P90, and empirical decay per target."""
    if motion_members.ndim == 3:
        motion_members = motion_members[None, ...]
    if motion_members.ndim != 4 or motion_members.shape[1] != 2:
        raise ValueError("motion_members must have shape (members, 2, H, W)")
    results: list[ArrivalWindow] = []
    for target in targets:
        arrivals = [
            value
            for member in motion_members
            if (
                value := _arrival_for_member(
                    storm.footprint,
                    target,
                    member,
                    horizon_steps=horizon_steps,
                    step_minutes=step_minutes,
                    km_per_cell=km_per_cell,
                )
            )
            is not None
        ]
        if arrivals:
            quantiles = np.quantile(arrivals, [0.1, 0.5, 0.9], method="higher").astype(int)
            t10, t50, t90 = (int(value) for value in quantiles)
        else:
            t10 = t50 = t90 = None
        p_decay = (
            survival.decay_probability(
                age_min=storm.age_frames * step_minutes,
                lead_min=horizon_steps * step_minutes,
            )
            if survival is not None
            else 0.0
        )
        results.append(
            ArrivalWindow(
                track_id=storm.track_id,
                target_id=target.target_id,
                p_arrival=len(arrivals) / motion_members.shape[0],
                t10=t10,
                t50=t50,
                t90=t90,
                p_decay=p_decay,
                radius_km=target.radius_km,
            )
        )
    return tuple(results)
