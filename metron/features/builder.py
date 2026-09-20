"""Assemble a contract-ordered, mask-aware feature bundle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
from metron.grids.masks import propagate_masks
from metron.qc.types import Provenance, QCResult, missing_qc_result

from .contracts import FeatureContract
from .ood import OODResult, OODScorer


def _group(name: str, result: QCResult | None = None) -> str:
    if "/" in name:
        return name.split("/", 1)[0]
    if "." in name:
        return name.split(".", 1)[0]
    if result is not None:
        return str(result.metadata.get("group", ""))
    return ""


@dataclass(frozen=True)
class FeatureBundle:
    tensor: np.ndarray
    names: tuple[str, ...]
    valid_mask: np.ndarray
    age_min: np.ndarray
    rung_hint: str
    missing: tuple[str, ...]
    provenance: tuple[Provenance, ...]
    ood: OODResult | None = None

    @property
    def tensors(self) -> dict[str, np.ndarray]:
        return {name: self.tensor[index] for index, name in enumerate(self.names)}

    @property
    def ood_score(self) -> float | None:
        return None if self.ood is None else self.ood.score

    def model_tensor(self) -> np.ndarray:
        """Return normalized channels followed by validity and age channels."""

        return np.concatenate(
            [self.tensor, self.valid_mask.astype(np.float32), np.minimum(self.age_min / 60.0, 2.0)],
            axis=0,
        )


def _group_valid(
    results: Mapping[str, QCResult], group: str, max_age: float, min_coverage: float
) -> bool:
    group_results = [result for name, result in results.items() if _group(name, result) == group]
    if not group_results:
        return False
    return any(
        not result.missing
        and result.age_min is not None
        and result.age_min <= max_age
        and result.coverage_fraction >= min_coverage
        for result in group_results
    )


def derive_rung(results: Mapping[str, QCResult]) -> str:
    """Apply the locked R0–R4 validity ladder to QC results."""

    sat = _group_valid(results, "sat", 45.0, 0.70)
    radar = _group_valid(results, "radar", 20.0, 0.30)
    ltg = _group_valid(results, "ltg", 10.0, 0.01)
    nwp = _group_valid(results, "nwp", float("inf"), 0.01)
    if radar and sat and ltg and nwp:
        return "R0"
    if sat and ltg and nwp:
        return "R1"
    if sat and nwp:
        return "R2"
    if nwp:
        return "R3"
    return "R4"


def build_feature_bundle(
    results: Mapping[str, QCResult],
    contract: FeatureContract,
    *,
    shape: tuple[int, int],
    domain_version: int,
    channel_version: int,
    ood_scorer: OODScorer | None = None,
) -> FeatureBundle:
    """Build features while making missing inputs explicit and reproducible."""

    live_names = tuple(results)
    if set(live_names) != set(contract.names):
        # Missing source data is represented by a QCResult, not by changing the
        # model's channel set. Extras are always a contract violation.
        missing_names = set(contract.names) - set(live_names)
        extra_names = set(live_names) - set(contract.names)
        if extra_names:
            contract.validate(
                live_names, domain_version=domain_version, channel_version=channel_version
            )
        for name in missing_names:
            group = _group(name)
            results = dict(results)
            results[name] = missing_qc_result(
                shape,
                source=group or "feature_builder",
                reason="missing_input",
                metadata={"group": group, "channel": name},
            )
        live_names = tuple(results)
    contract.validate(live_names, domain_version=domain_version, channel_version=channel_version)
    for name, result in results.items():
        if result.shape != shape:
            raise ValueError(f"{name} has shape {result.shape}, expected {shape}")
    arrays = {name: result.model_values() for name, result in results.items()}
    masks = {name: result.valid_mask.astype(bool) for name, result in results.items()}
    tensor = contract.normalize(
        arrays,
        masks=masks,
        domain_version=domain_version,
        channel_version=channel_version,
    )
    mask_bundle = propagate_masks(results, shape=shape)
    valid_mask = np.stack([mask_bundle.valid[name] for name in contract.names], axis=0)
    ages = np.stack([mask_bundle.age_min[name] for name in contract.names], axis=0)
    ood = None if ood_scorer is None else ood_scorer.score(tensor)
    missing = tuple(name for name in contract.names if results[name].missing)
    provenance = tuple(results[name].provenance for name in contract.names)
    return FeatureBundle(
        tensor=tensor,
        names=contract.names,
        valid_mask=valid_mask,
        age_min=ages,
        rung_hint=derive_rung(results),
        missing=missing,
        provenance=provenance,
        ood=ood,
    )
