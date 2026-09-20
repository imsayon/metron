"""Name-based feature contracts and model-safe normalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np


class FeatureContractError(ValueError):
    """The live feature set cannot be safely used by a trained model."""


@dataclass(frozen=True)
class FeatureContract:
    names: tuple[str, ...]
    means: tuple[float, ...]
    stds: tuple[float, ...]
    mins: tuple[float, ...]
    maxs: tuple[float, ...]
    fill_policy: str = "zero_with_mask"
    domain_version: int = 1
    channel_version: int = 1

    def __post_init__(self) -> None:
        names = tuple(self.names)
        object.__setattr__(self, "names", names)
        for field_name in ("means", "stds", "mins", "maxs"):
            object.__setattr__(self, field_name, tuple(float(value) for value in getattr(self, field_name)))
        if not names or len(set(names)) != len(names):
            raise FeatureContractError("feature names must be non-empty and unique")
        length = len(names)
        if any(len(getattr(self, field_name)) != length for field_name in ("means", "stds", "mins", "maxs")):
            raise FeatureContractError("feature statistics must match names")
        if self.fill_policy != "zero_with_mask":
            raise FeatureContractError(f"unsupported fill policy: {self.fill_policy}")
        if self.domain_version <= 0 or self.channel_version <= 0:
            raise FeatureContractError("contract versions must be positive")
        if any(std <= 0 or not np.isfinite(std) for std in self.stds):
            raise FeatureContractError("feature standard deviations must be finite and positive")
        if any(low > high for low, high in zip(self.mins, self.maxs)):
            raise FeatureContractError("feature minimum cannot exceed maximum")

    def validate(
        self,
        live_names: Sequence[str],
        *,
        domain_version: int | None = None,
        channel_version: int | None = None,
    ) -> tuple[int, ...]:
        """Validate a live set and return its index for contract order."""

        live = tuple(live_names)
        if len(set(live)) != len(live):
            raise FeatureContractError("live feature names contain duplicates")
        if set(live) != set(self.names):
            missing = sorted(set(self.names) - set(live))
            extra = sorted(set(live) - set(self.names))
            raise FeatureContractError(f"feature names mismatch; missing={missing}, extra={extra}")
        if domain_version is not None and domain_version != self.domain_version:
            raise FeatureContractError(
                f"domain_version mismatch: live={domain_version}, contract={self.domain_version}"
            )
        if channel_version is not None and channel_version != self.channel_version:
            raise FeatureContractError(
                f"channel_version mismatch: live={channel_version}, contract={self.channel_version}"
            )
        positions = {name: index for index, name in enumerate(live)}
        return tuple(positions[name] for name in self.names)

    def normalize(
        self,
        features: Mapping[str, np.ndarray],
        *,
        masks: Mapping[str, np.ndarray] | None = None,
        domain_version: int | None = None,
        channel_version: int | None = None,
    ) -> np.ndarray:
        """Stack features in contract order and replace missing values by zero."""

        self.validate(tuple(features), domain_version=domain_version, channel_version=channel_version)
        arrays = [np.asarray(features[name], dtype=np.float32) for name in self.names]
        shape = arrays[0].shape
        if any(array.shape != shape for array in arrays):
            raise FeatureContractError("feature arrays must all have the same shape")
        normalized: list[np.ndarray] = []
        for index, (name, array) in enumerate(zip(self.names, arrays)):
            valid = np.isfinite(array) & (array >= self.mins[index]) & (array <= self.maxs[index])
            if masks is not None:
                if name not in masks or np.asarray(masks[name]).shape != shape:
                    raise FeatureContractError(f"mask missing or has wrong shape for {name}")
                valid &= np.asarray(masks[name], dtype=bool)
            scaled = (array - self.means[index]) / self.stds[index]
            normalized.append(np.where(valid, scaled, 0.0).astype(np.float32, copy=False))
        return np.stack(normalized, axis=0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "names": list(self.names),
            "means": list(self.means),
            "stds": list(self.stds),
            "mins": list(self.mins),
            "maxs": list(self.maxs),
            "fill_policy": self.fill_policy,
            "domain_version": self.domain_version,
            "channel_version": self.channel_version,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "FeatureContract":
        return cls(
            names=tuple(raw["names"]),
            means=tuple(raw["means"]),
            stds=tuple(raw["stds"]),
            mins=tuple(raw["mins"]),
            maxs=tuple(raw["maxs"]),
            fill_policy=str(raw.get("fill_policy", "zero_with_mask")),
            domain_version=int(raw["domain_version"]),
            channel_version=int(raw["channel_version"]),
        )
