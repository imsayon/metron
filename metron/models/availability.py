"""Gates that stop training claims when the specified data is absent."""

from __future__ import annotations

from dataclasses import dataclass

from metron.labels import LabelEvent


class TrainingUnavailable(RuntimeError):
    """The requested module cannot be trained from the supplied inputs."""


@dataclass(frozen=True)
class DatasetAvailability:
    data_manifest_hash: str
    labels: tuple[LabelEvent, ...] = ()
    synthetic: bool = False
    channels: frozenset[str] = frozenset()

    def require_training(self, module: str, *, required_channels: set[str] | None = None) -> None:
        if not self.data_manifest_hash.strip():
            raise TrainingUnavailable(f"{module}: data_manifest_hash is required")
        if self.synthetic:
            raise TrainingUnavailable(f"{module}: synthetic data cannot support a training claim")
        missing = (required_channels or set()) - self.channels
        if missing:
            raise TrainingUnavailable(f"{module}: missing channels {sorted(missing)}")
        real_labels = [label for label in self.labels if not label.research_only]
        if not real_labels:
            raise TrainingUnavailable(f"{module}: no non-synthetic, non-proxy labels are available")
