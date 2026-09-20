"""M4 hail-signature rules; calibrated probability awaits real labels."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import Abstention


@dataclass(frozen=True)
class HailFeatures:
    mesh_mm: float | None = None
    z_m20c_dbz: float | None = None
    freezing_level_m: float | None = None
    shear06_ms: float | None = None
    tti: float | None = None
    radar_valid: bool = False


@dataclass(frozen=True)
class HailResult:
    signature_present: bool | None
    probability: float | None
    abstentions: tuple[Abstention, ...] = ()
    research_only: bool = True


def hail_signature(features: HailFeatures) -> HailResult:
    if not features.radar_valid:
        return HailResult(
            None,
            None,
            (Abstention("M4", "no_radar", "hail probability requires radar"),),
        )
    radar_signal = (features.mesh_mm or 0) >= 20 or (
        (features.z_m20c_dbz or 0) >= 55 and (features.freezing_level_m or float("inf")) <= 4500
    )
    environment_signal = (features.shear06_ms or 0) >= 10 or (features.tti or 0) >= 46
    return HailResult(signature_present=radar_signal and environment_signal, probability=None)
