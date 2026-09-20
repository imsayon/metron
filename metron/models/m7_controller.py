"""Rung selection and explicit degradation behavior."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import Abstention


@dataclass(frozen=True)
class ModalityStatus:
    satellite_valid: bool
    satellite_age_min: float
    radar_valid: bool
    radar_age_min: float
    radar_coverage_fraction: float
    lightning_valid: bool
    lightning_age_min: float
    lightning_health: int
    nwp_valid: bool
    ood: bool = False
    contract_ok: bool = True


@dataclass(frozen=True)
class ControllerDecision:
    rung: str
    ood_flag: bool
    abstentions: tuple[Abstention, ...]


def choose_rung(status: ModalityStatus) -> ControllerDecision:
    sat = status.satellite_valid and status.satellite_age_min <= 45
    radar = (
        status.radar_valid
        and status.radar_age_min <= 20
        and status.radar_coverage_fraction >= 0.30
    )
    lightning = (
        status.lightning_valid
        and status.lightning_age_min <= 10
        and status.lightning_health > 0
    )
    nwp = status.nwp_valid
    if status.ood:
        return ControllerDecision("R4", True, (Abstention("M7", "ood", "input is outside training support"),))
    if not status.contract_ok:
        return ControllerDecision("R4", False, (Abstention("M7", "contract_violation", "feature contract mismatch"),))
    if radar and sat and lightning and nwp:
        return ControllerDecision("R0", False, ())
    if sat and lightning and nwp:
        return ControllerDecision("R1", False, (Abstention("M4", "no_radar", "hail module disabled"), Abstention("M5", "no_velocity", "velocity not guaranteed")))
    if sat and nwp:
        return ControllerDecision("R2", False, (Abstention("M4", "no_radar", "hail module disabled"), Abstention("M5", "no_velocity", "velocity not available")))
    if nwp:
        return ControllerDecision("R3", False, (Abstention("M1", "sat_missing", "no observation-driven arrival"),))
    return ControllerDecision("R4", False, (Abstention("M7", "nwp_missing", "no valid rung"),))
