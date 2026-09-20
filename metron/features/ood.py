"""Lightweight Mahalanobis OOD scoring for feature stems."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def mahalanobis_distance(
    value: np.ndarray,
    mean: np.ndarray,
    covariance: np.ndarray | None = None,
    *,
    regularization: float = 1e-6,
) -> float:
    x = np.asarray(value, dtype=np.float64).reshape(-1)
    mu = np.asarray(mean, dtype=np.float64).reshape(-1)
    if x.shape != mu.shape:
        raise ValueError("value and mean must have the same number of elements")
    if not np.isfinite(x).all() or not np.isfinite(mu).all():
        raise ValueError("OOD inputs must be finite")
    if covariance is None:
        inverse = np.eye(x.size, dtype=np.float64)
    else:
        cov = np.asarray(covariance, dtype=np.float64)
        if cov.ndim == 1:
            if cov.shape != x.shape or np.any(cov <= 0):
                raise ValueError("diagonal covariance must be positive and match the value shape")
            inverse = np.diag(1.0 / (cov + regularization))
        elif cov.shape == (x.size, x.size):
            inverse = np.linalg.pinv(cov + np.eye(x.size) * regularization)
        else:
            raise ValueError("covariance must be a diagonal vector or square matrix")
    delta = x - mu
    squared = float(delta @ inverse @ delta)
    return float(np.sqrt(max(0.0, squared)))


@dataclass(frozen=True)
class OODResult:
    score: float
    threshold: float
    is_ood: bool


@dataclass(frozen=True)
class OODScorer:
    reference_mean: np.ndarray
    reference_covariance: np.ndarray | None
    threshold: float

    def __post_init__(self) -> None:
        mean = np.asarray(self.reference_mean, dtype=np.float64).reshape(-1)
        object.__setattr__(self, "reference_mean", mean)
        if self.reference_covariance is not None:
            object.__setattr__(self, "reference_covariance", np.asarray(self.reference_covariance, dtype=np.float64))
        if self.threshold < 0:
            raise ValueError("OOD threshold must be non-negative")

    def score(self, features: np.ndarray) -> OODResult:
        array = np.asarray(features, dtype=np.float64)
        vector = array if array.ndim == 1 else array.reshape(array.shape[0], -1).mean(axis=1)
        value = mahalanobis_distance(vector, self.reference_mean, self.reference_covariance)
        return OODResult(score=value, threshold=float(self.threshold), is_ood=value > self.threshold)


def score_features(
    features: np.ndarray,
    *,
    reference_mean: np.ndarray,
    reference_covariance: np.ndarray | None = None,
    threshold: float,
) -> OODResult:
    return OODScorer(reference_mean, reference_covariance, threshold).score(features)
