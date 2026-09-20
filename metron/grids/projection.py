"""Deterministic grid projection helpers.

The production dependency may use pyproj, but the LCC equations here keep
projection and orientation tests runnable in a minimal environment.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .config import DomainConfig


WGS84_A = 6_378_137.0
WGS84_B = 6_356_752.314245
WGS84_E = math.sqrt(1.0 - (WGS84_B / WGS84_A) ** 2)


def _m(phi: np.ndarray | float) -> np.ndarray | float:
    sin_phi = np.sin(phi) if isinstance(phi, np.ndarray) else math.sin(phi)
    return (np.cos(phi) if isinstance(phi, np.ndarray) else math.cos(phi)) / np.sqrt(
        1.0 - WGS84_E**2 * sin_phi**2
    )


def _t(phi: np.ndarray | float) -> np.ndarray | float:
    sin_phi = np.sin(phi) if isinstance(phi, np.ndarray) else math.sin(phi)
    tangent = np.tan(math.pi / 4.0 - phi / 2.0)
    return tangent / ((1.0 - WGS84_E * sin_phi) / (1.0 + WGS84_E * sin_phi)) ** (WGS84_E / 2.0)


def _lcc_constants(lat_0: float, lat_1: float, lat_2: float) -> tuple[float, float, float]:
    phi0, phi1, phi2 = np.radians([lat_0, lat_1, lat_2])
    m1, m2 = _m(phi1), _m(phi2)
    t1, t2, t0 = _t(phi1), _t(phi2), _t(phi0)
    if abs(lat_1 - lat_2) < 1e-12:
        n = math.sin(float(phi1))
    else:
        n = math.log(float(m1) / float(m2)) / math.log(float(t1) / float(t2))
    f = float(m1) / (n * float(t1) ** n)
    rho0 = WGS84_A * f * float(t0) ** n
    return n, f, rho0


def lcc_forward(
    lat_deg: np.ndarray | float,
    lon_deg: np.ndarray | float,
    *,
    lat_0: float,
    lon_0: float,
    lat_1: float,
    lat_2: float,
) -> tuple[np.ndarray | float, np.ndarray | float]:
    """Project WGS84 latitude/longitude to LCC metres."""

    lat = np.radians(lat_deg)
    lon = np.radians(lon_deg)
    n, f, rho0 = _lcc_constants(lat_0, lat_1, lat_2)
    rho = WGS84_A * f * _t(lat) ** n
    theta = n * (lon - math.radians(lon_0))
    x = rho * np.sin(theta)
    y = rho0 - rho * np.cos(theta)
    if np.ndim(x) == 0:
        return float(x), float(y)
    return x, y


def project_latlon(
    domain: "DomainConfig", lat_deg: np.ndarray | float, lon_deg: np.ndarray | float
):
    if domain.projection == "equirectangular":
        return np.asarray(lon_deg, dtype=float), np.asarray(lat_deg, dtype=float)
    return lcc_forward(lat_deg, lon_deg, **domain.projection_parameters)


def grid_centers(domain: "DomainConfig") -> tuple[np.ndarray, np.ndarray]:
    """Return 2-D ``x, y`` cell-centre coordinates in storage orientation."""

    transform = domain.geotransform
    x0, dx, _, y0, _, dy = transform
    x = x0 + (np.arange(domain.nx, dtype=float) + 0.5) * dx
    y = y0 + (np.arange(domain.ny, dtype=float) + 0.5) * dy
    return np.meshgrid(x, y)


def latlon_to_grid(
    domain: "DomainConfig", lat_deg: np.ndarray | float, lon_deg: np.ndarray | float
) -> tuple[np.ndarray | float, np.ndarray | float]:
    """Return fractional ``row, col`` indices for WGS84 coordinates."""

    x, y = project_latlon(domain, lat_deg, lon_deg)
    x0, dx, _, y0, _, dy = domain.geotransform
    col = (np.asarray(x) - x0) / dx
    row = (np.asarray(y) - y0) / dy
    if np.ndim(row) == 0:
        return float(row), float(col)
    return row, col
