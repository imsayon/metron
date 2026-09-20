"""Feature contracts, OOD scoring, and mask-aware tensor assembly."""

from .builder import FeatureBundle, build_feature_bundle, derive_rung
from .contracts import FeatureContract, FeatureContractError
from .ood import OODResult, OODScorer, mahalanobis_distance

__all__ = [
    "FeatureBundle",
    "FeatureContract",
    "FeatureContractError",
    "OODResult",
    "OODScorer",
    "build_feature_bundle",
    "derive_rung",
    "mahalanobis_distance",
]
