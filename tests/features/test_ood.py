import numpy as np

from metron.features.ood import OODScorer, mahalanobis_distance


def test_mahalanobis_zero_at_reference_mean():
    assert mahalanobis_distance(np.array([1.0, 2.0]), np.array([1.0, 2.0])) == 0.0


def test_ood_score_is_deterministic_and_thresholded():
    scorer = OODScorer(np.zeros(2), np.ones(2), threshold=1.0)
    result = scorer.score(np.array([[2.0, 0.0], [2.0, 0.0]], dtype=np.float32))
    assert result.score > 1.0
    assert result.is_ood
