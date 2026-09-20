from metron.grids.config import load_domain
from metron.grids.projection import grid_centers, latlon_to_grid


def test_locked_domain_dimensions_and_row_orientation():
    pilot_e = load_domain("pilot_e")
    assert pilot_e.shape == (450, 500)
    x, y = grid_centers(pilot_e)
    assert x.shape == y.shape == pilot_e.shape
    assert y[0, 0] > y[1, 0]
    assert x[0, 1] > x[0, 0]


def test_lcc_origin_maps_to_expected_fractional_cell():
    pilot_e = load_domain("pilot_e")
    row, col = latlon_to_grid(pilot_e, 23.0, 87.0)
    assert abs(row - 225.0) < 1e-6
    assert abs(col - 250.0) < 1e-6


def test_national_grid_uses_north_to_south_equirectangular_indices():
    national = load_domain("national_s")
    row, col = latlon_to_grid(national, 37.98, 66.02)
    assert abs(row - 0.5) < 1e-6
    assert abs(col - 0.5) < 1e-6
