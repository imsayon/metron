"""Small contracts shared by F3 modules.

The contracts intentionally keep provenance and citable-metric checks close to
the model outputs. A score without a frozen figure reference is not a claim.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

FIGURE_ID = re.compile(r"^F-[A-Za-z0-9_]+-[A-Za-z0-9_]+-[A-Za-z0-9_]+-[A-Za-z0-9_]+-[A-Za-z0-9_]+$")
VALID_RUNGS = frozenset({"R0", "R1", "R2", "R3", "R4"})
VALID_REASON_CODES = frozenset(
    {
        "no_radar",
        "no_velocity",
        "sat_stale",
        "sat_missing",
        "ltg_unavailable",
        "nwp_missing",
        "ood",
        "contract_violation",
        "poor_motion",
        "cycle_overrun",
        "uncalibrated_regime",
        "research_only",
    }
)


class ContractValidationError(ValueError):
    """Raised when a persisted or runtime model contract is invalid."""


def validate_figure_reference(figure_id: str | None, *, frozen: bool) -> str:
    if not frozen:
        raise ContractValidationError("metrics are citable only from frozen runs")
    if not figure_id or not FIGURE_ID.fullmatch(figure_id):
        raise ContractValidationError(f"invalid frozen figure id: {figure_id!r}")
    return figure_id


def _utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ContractValidationError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class FeatureContract:
    names: tuple[str, ...]
    means: Mapping[str, float] = field(default_factory=dict)
    stds: Mapping[str, float] = field(default_factory=dict)
    mins: Mapping[str, float] = field(default_factory=dict)
    maxs: Mapping[str, float] = field(default_factory=dict)
    domain_version: int = 1
    channel_version: int = 1
    fill_policy: str = "zero_with_mask"

    def validate(self) -> "FeatureContract":
        if not self.names or len(set(self.names)) != len(self.names):
            raise ContractValidationError("feature names must be non-empty and unique")
        if self.domain_version < 1 or self.channel_version < 1:
            raise ContractValidationError("domain/channel versions must be positive")
        if self.fill_policy != "zero_with_mask":
            raise ContractValidationError("only zero_with_mask is supported")
        for name in self.names:
            if name not in self.means or name not in self.stds:
                raise ContractValidationError(f"missing normalization statistics for {name}")
            if self.stds[name] <= 0:
                raise ContractValidationError(f"std must be positive for {name}")
        return self

    def check_names(self, values: Mapping[str, Any]) -> None:
        self.validate()
        expected = set(self.names)
        actual = set(values)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise ContractValidationError(f"feature names differ: missing={missing}, extra={extra}")

    def digest(self) -> str:
        self.validate()
        payload = {
            "names": self.names,
            "means": dict(sorted(self.means.items())),
            "stds": dict(sorted(self.stds.items())),
            "mins": dict(sorted(self.mins.items())),
            "maxs": dict(sorted(self.maxs.items())),
            "domain_version": self.domain_version,
            "channel_version": self.channel_version,
            "fill_policy": self.fill_policy,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class Provenance:
    model_version: str
    data_manifest_hash: str
    issue_time: datetime
    rung: str
    synthetic: bool = False
    skill_ref: str | None = None
    frozen: bool = False

    def validate(self) -> "Provenance":
        if not self.model_version.strip() or not self.data_manifest_hash.strip():
            raise ContractValidationError("model_version and data_manifest_hash are required")
        if self.rung not in VALID_RUNGS:
            raise ContractValidationError(f"unknown rung: {self.rung}")
        issue_time = _utc(self.issue_time)
        if self.skill_ref is not None:
            validate_figure_reference(self.skill_ref, frozen=self.frozen)
        if self.synthetic and self.skill_ref is not None:
            raise ContractValidationError("synthetic outputs cannot carry citable skill")
        return Provenance(
            model_version=self.model_version,
            data_manifest_hash=self.data_manifest_hash,
            issue_time=issue_time,
            rung=self.rung,
            synthetic=self.synthetic,
            skill_ref=self.skill_ref,
            frozen=self.frozen,
        )


@dataclass(frozen=True)
class Abstention:
    module: str
    reason_code: str
    detail: str = ""

    def validate(self) -> "Abstention":
        if not self.module.strip():
            raise ContractValidationError("abstention module is required")
        if self.reason_code not in VALID_REASON_CODES:
            raise ContractValidationError(f"unknown abstention reason: {self.reason_code}")
        return self


@dataclass(frozen=True)
class ModuleOutput:
    arrays: Mapping[str, Any]
    tables: Mapping[str, Any]
    provenance: Provenance
    abstentions: tuple[Abstention, ...] = ()

    def validate(self) -> "ModuleOutput":
        self.provenance.validate()
        for abstention in self.abstentions:
            abstention.validate()
        return self


@dataclass(frozen=True)
class ModelVersion:
    model_version: str
    module: str
    git_sha: str
    data_manifest_hash: str
    feature_contract: FeatureContract
    definition_version: str = "1"
    channel_version: int = 1
    domain_version: int = 1
    research_only: bool = True
    frozen_figure_ids: tuple[str, ...] = ()

    def validate(self) -> "ModelVersion":
        if not self.model_version.strip() or not self.module.strip() or not self.git_sha.strip():
            raise ContractValidationError("model identity fields are required")
        if not self.data_manifest_hash.strip():
            raise ContractValidationError("data_manifest_hash is required")
        if self.definition_version != "1" or self.channel_version < 1 or self.domain_version < 1:
            raise ContractValidationError("definition/channel/domain versions are invalid")
        self.feature_contract.validate()
        if self.feature_contract.domain_version != self.domain_version:
            raise ContractValidationError("feature/domain version mismatch")
        if self.feature_contract.channel_version != self.channel_version:
            raise ContractValidationError("feature/channel version mismatch")
        for figure_id in self.frozen_figure_ids:
            validate_figure_reference(figure_id, frozen=True)
        if self.frozen_figure_ids and self.research_only:
            raise ContractValidationError("research-only models cannot publish frozen skill")
        return self
