"""M2 input masking and training gate.

The learned U-Net is deliberately not fabricated here: Indian ILLN/radar
labels are not present. The reusable part is modality-dropout behavior and a
hard gate that prevents a synthetic fixture from becoming a model claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from .availability import DatasetAvailability

MODALITY_DROP_PROB = {"sat": 0.1, "radar": 0.5, "ltg": 0.3, "env": 0.0}


@dataclass(frozen=True)
class M2Input:
    modalities: Mapping[str, np.ndarray]
    valid: Mapping[str, bool]
    synthetic: bool = False


@dataclass(frozen=True)
class M2MaskedInput:
    modalities: Mapping[str, np.ndarray]
    valid: Mapping[str, bool]
    dropped: tuple[str, ...]


def apply_modality_dropout(
    value: M2Input,
    *,
    seed: int,
    probabilities: Mapping[str, float] = MODALITY_DROP_PROB,
) -> M2MaskedInput:
    """Zero dropped stems and never drop every modality."""
    if not value.modalities:
        raise ValueError("at least one modality is required")
    if any(probability < 0 or probability > 1 for probability in probabilities.values()):
        raise ValueError("dropout probabilities must be in [0, 1]")
    rng = np.random.default_rng(seed)
    dropped = {
        name
        for name, array in value.modalities.items()
        if value.valid.get(name, False) and rng.random() < probabilities.get(name, 0.0)
    }
    usable = [name for name in value.modalities if value.valid.get(name, False)]
    if usable and len(dropped) == len(usable):
        keep = usable[int(rng.integers(0, len(usable)))]
        dropped.remove(keep)
    masked = {
        name: np.zeros_like(array) if name in dropped else np.asarray(array).copy()
        for name, array in value.modalities.items()
    }
    valid = {
        name: bool(value.valid.get(name, False) and name not in dropped)
        for name in value.modalities
    }
    return M2MaskedInput(masked, valid, tuple(sorted(dropped)))


def require_m2_training(availability: DatasetAvailability) -> None:
    availability.require_training(
        "M2",
        required_channels={"ir1", "ir2", "wv"},
    )
