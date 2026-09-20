import numpy as np

from metron.grids.regrid import regrid_extreme


def test_minimum_and_maximum_resampling_keep_extremes():
    source = np.array(
        [
            [-40.0, 1.0, 2.0, 3.0],
            [4.0, 5.0, 6.0, 7.0],
            [8.0, 9.0, 10.0, 11.0],
            [12.0, 13.0, 14.0, 85.0],
        ],
        dtype=np.float32,
    )
    cold = regrid_extreme(source, (2, 2), kind="minimum")
    intense = regrid_extreme(source, (2, 2), kind="maximum")
    assert np.nanmin(cold) == np.min(source)
    assert np.nanmax(intense) == np.max(source)


def test_invalid_pixels_are_not_used_by_extreme_kernel():
    source = np.array([[100.0, 1.0], [2.0, 3.0]], dtype=np.float32)
    valid = np.array([[False, True], [True, True]])
    output = regrid_extreme(source, (1, 1), kind="maximum", valid_mask=valid)
    assert output[0, 0] == 3.0


def test_extreme_invariants_hold_for_deterministic_random_fields():
    rng = np.random.default_rng(26084)
    for target_shape in ((1, 1), (2, 3), (5, 7)):
        source = rng.normal(size=(8, 11)).astype(np.float32)
        minimum = regrid_extreme(source, target_shape, kind="minimum")
        maximum = regrid_extreme(source, target_shape, kind="maximum")
        assert np.nanmin(minimum) >= np.min(source) - 0.5
        assert np.nanmax(maximum) <= np.max(source) + 0.5
