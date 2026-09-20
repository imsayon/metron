"""Reproducible verification and figure identifiers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from metron.common.hashing import sha256_file, sha256_json
from metron.common.manifest import DataManifest


def data_manifest_hash(
    manifest_ids: Sequence[str],
    *,
    channel_version: int,
    domain_version: int,
    definition_version: int,
) -> str:
    return DataManifest(
        tuple(manifest_ids),
        channel_version=channel_version,
        domain_version=domain_version,
        definition_version=definition_version,
    ).data_manifest_hash


def figure_id(module: str, metric: str, axis: str, domain: str, period: str) -> str:
    parts = (module, metric, axis, domain, period)
    if any(not part.strip() for part in parts):
        raise ValueError("figure ID components must not be empty")
    return "F-" + "-".join(parts)


def verification_run_id(
    *,
    data_manifest_hash: str,
    channel_version: int,
    definition_version: int,
    git_sha: str,
    spec: Mapping[str, Any],
    seed: int,
    model_versions: Sequence[str] = (),
) -> str:
    payload = {
        "data_manifest_hash": data_manifest_hash,
        "channel_version": channel_version,
        "definition_version": definition_version,
        "git_sha": git_sha,
        "model_versions": sorted(model_versions),
        "seed": seed,
        "spec": spec,
    }
    return "vr-" + sha256_json(payload)[:16]


@dataclass(frozen=True, slots=True)
class VerificationRun:
    run_id: str
    frozen: bool
    data_manifest_hash: str
    channel_version: int
    definition_version: int
    git_sha: str
    seed: int
    model_versions: tuple[str, ...] = ()
    spec_hash: str = ""

    @property
    def citable(self) -> bool:
        return self.frozen

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "frozen": self.frozen,
            "data_manifest_hash": self.data_manifest_hash,
            "channel_version": self.channel_version,
            "definition_version": self.definition_version,
            "git_sha": self.git_sha,
            "seed": self.seed,
            "model_versions": list(self.model_versions),
            "spec_hash": self.spec_hash,
        }


stable_hash = sha256_json
run_id = verification_run_id
make_figure_id = figure_id

__all__ = [
    "VerificationRun",
    "data_manifest_hash",
    "figure_id",
    "make_figure_id",
    "run_id",
    "sha256_file",
    "stable_hash",
    "verification_run_id",
]
