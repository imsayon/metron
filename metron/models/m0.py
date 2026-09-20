"""M0 motion/ensemble contract with a deterministic NumPy fallback.

`pysteps` is an optional runtime dependency. This repository currently has no
meteorological inputs, so the fallback is useful for fixture checks only and
is marked research-only in its output provenance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

from .baselines import advect, persistence
from .contracts import Abstention
from .data import AvailableFrame, DataAvailabilityError, select_available_frames


@dataclass(frozen=True)
class M0Config:
    horizon_steps: int = 36
    members: int = 24
    seed: int = 0
    noise_scale: float = 0.02

    def validate(self) -> "M0Config":
        if self.horizon_steps < 1 or self.members < 1 or self.noise_scale < 0:
            raise ValueError("invalid M0 configuration")
        return self


@dataclass(frozen=True)
class M0Input:
    frames: tuple[AvailableFrame, ...]
    issue_time: datetime
    motion_uv: np.ndarray
    motion_quality: float
    coverage_fraction: float
    rung: str = "R0"


@dataclass(frozen=True)
class M0Result:
    deterministic: np.ndarray
    members: np.ndarray
    motion_uv: np.ndarray
    motion_quality: float
    backend: str
    synthetic: bool
    abstentions: tuple[Abstention, ...] = ()

    @property
    def research_only(self) -> bool:
        return self.synthetic or self.backend != "pysteps"

    def exceedance_probability(self, thresholds: tuple[float, ...]) -> np.ndarray:
        """Return ``(threshold, lead, y, x)`` probabilities for fixture use."""
        return np.stack([(self.members >= threshold).mean(axis=0) for threshold in thresholds])


def _validate_input(value: M0Input) -> None:
    if value.motion_uv.ndim != 3 or value.motion_uv.shape[0] != 2:
        raise ValueError("motion_uv must have shape (2, H, W)")
    if not 0 <= value.motion_quality <= 1 or not 0 <= value.coverage_fraction <= 1:
        raise ValueError("motion_quality and coverage_fraction must be in [0, 1]")


def run_m0(value: M0Input, config: M0Config | None = None) -> M0Result:
    """Run M0 or its explicit persistence fallback at one issue time."""
    config = M0Config() if config is None else config
    config.validate()
    _validate_input(value)
    try:
        frames = select_available_frames(value.frames, issue_time=value.issue_time, count=2)
        insufficient_history = False
    except DataAvailabilityError:
        try:
            frames = select_available_frames(value.frames, issue_time=value.issue_time, count=1)
        except DataAvailabilityError as exc:
            raise DataAvailabilityError("M0 needs one frame available at issue time") from exc
        insufficient_history = True
    latest = frames[-1]
    field = latest.values.astype(np.float32, copy=False)
    motion = value.motion_uv.astype(np.float32, copy=False)
    if motion.shape != (2, *field.shape):
        raise ValueError("motion_uv must match the latest frame shape")
    fallback = insufficient_history or value.motion_quality < 0.3 or value.coverage_fraction < 0.3
    if fallback:
        deterministic = persistence(field, config.horizon_steps)
        members = np.repeat(deterministic[None, ...], config.members, axis=0)
        return M0Result(
            deterministic=deterministic,
            members=members,
            motion_uv=motion,
            motion_quality=value.motion_quality,
            backend="persistence_fallback",
            synthetic=any(frame.synthetic for frame in frames),
            abstentions=(
                Abstention(
                    "M0", "poor_motion", "insufficient history, motion quality, or coverage"
                ),
            ),
        )

    deterministic = np.stack(
        [advect(field, motion, step) for step in range(1, config.horizon_steps + 1)]
    )
    rng = np.random.default_rng(config.seed)
    spread = float(np.std(field)) * config.noise_scale
    members = np.empty((config.members, *deterministic.shape), dtype=np.float32)
    for index in range(config.members):
        noise = rng.normal(0, spread, deterministic.shape).astype(np.float32)
        members[index] = np.maximum(deterministic + noise, 0)
    return M0Result(
        deterministic=deterministic,
        members=members,
        motion_uv=motion,
        motion_quality=value.motion_quality,
        backend="numpy_fallback",
        synthetic=any(frame.synthetic for frame in frames),
    )
