"""Validated loaders for the versioned grid and channel contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs"


def _read_yaml(path: Path) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, Mapping):
        raise ValueError(f"expected a mapping in {path}")
    return data


def _positive(value: Any, field: str, *, integer: bool = False) -> int | float:
    if integer:
        result = int(value)
        if result <= 0 or result != value:
            raise ValueError(f"{field} must be a positive integer")
    else:
        result = float(value)
        if result <= 0:
            raise ValueError(f"{field} must be positive")
    return result


def _crs_params(crs: str) -> dict[str, float]:
    return {
        key: float(value) for key, value in re.findall(r"\+(lat_0|lon_0|lat_1|lat_2)=([^ ]+)", crs)
    }


@dataclass(frozen=True)
class DomainConfig:
    name: str
    version: int
    crs: str
    nx: int
    ny: int
    cycle_s: int
    sat_cadence_s: int
    dx_m: float | None = None
    dx_deg: float | None = None
    upper_left_xy_m: tuple[float, float] | None = None
    upper_left_lonlat: tuple[float, float] | None = None

    @property
    def shape(self) -> tuple[int, int]:
        return (self.ny, self.nx)

    @property
    def projection(self) -> str:
        return "equirectangular" if self.crs.upper() == "EPSG:4326" else "lcc"

    @property
    def spacing(self) -> float:
        if self.dx_m is not None:
            return self.dx_m
        if self.dx_deg is not None:
            return self.dx_deg
        raise ValueError(f"{self.name} has no grid spacing")

    @property
    def geotransform(self) -> tuple[float, float, float, float, float, float]:
        """GDAL geotransform for an upper-left, north-to-south grid."""

        if self.projection == "lcc":
            assert self.upper_left_xy_m is not None and self.dx_m is not None
            x, y = self.upper_left_xy_m
            return (x, self.dx_m, 0.0, y, 0.0, -self.dx_m)
        assert self.upper_left_lonlat is not None and self.dx_deg is not None
        lon, lat = self.upper_left_lonlat
        return (lon, self.dx_deg, 0.0, lat, 0.0, -self.dx_deg)

    @property
    def projection_parameters(self) -> dict[str, float]:
        if self.projection != "lcc":
            return {}
        params = _crs_params(self.crs)
        required = {"lat_0", "lon_0", "lat_1", "lat_2"}
        if required - params.keys():
            raise ValueError(f"{self.name} LCC CRS is missing {sorted(required - params.keys())}")
        return params

    @property
    def crs_wkt(self) -> str:
        """Return WKT when pyproj exists, otherwise the locked CRS string.

        The fallback is intentional: metadata remains self-describing in the
        lightweight test environment without pretending a PROJ conversion ran.
        """

        try:
            from pyproj import CRS  # type: ignore[import-not-found]

            return CRS.from_user_input(self.crs).to_wkt()
        except (ImportError, RuntimeError, ValueError):
            return self.crs

    @classmethod
    def from_mapping(cls, name: str, raw: Mapping[str, Any]) -> "DomainConfig":
        version = _positive(raw.get("version"), f"{name}.version", integer=True)
        nx = _positive(raw.get("nx"), f"{name}.nx", integer=True)
        ny = _positive(raw.get("ny"), f"{name}.ny", integer=True)
        cycle_s = _positive(raw.get("cycle_s"), f"{name}.cycle_s", integer=True)
        sat_cadence_s = _positive(raw.get("sat_cadence_s"), f"{name}.sat_cadence_s", integer=True)
        crs = str(raw.get("crs", "")).strip()
        if not crs:
            raise ValueError(f"{name}.crs is required")
        dx_m = float(raw["dx_m"]) if "dx_m" in raw else None
        dx_deg = float(raw["dx_deg"]) if "dx_deg" in raw else None
        if (dx_m is None) == (dx_deg is None):
            raise ValueError(f"{name} must define exactly one of dx_m or dx_deg")
        upper_left_xy_m = (
            tuple(float(v) for v in raw["upper_left_xy_m"]) if "upper_left_xy_m" in raw else None
        )
        upper_left_lonlat = (
            tuple(float(v) for v in raw["upper_left_lonlat"])
            if "upper_left_lonlat" in raw
            else None
        )
        if (upper_left_xy_m is None) == (upper_left_lonlat is None):
            raise ValueError(f"{name} must define exactly one upper-left coordinate")
        if len(upper_left_xy_m or upper_left_lonlat or ()) != 2:
            raise ValueError(f"{name} upper-left coordinate must have two values")
        return cls(
            name=name,
            version=int(version),
            crs=crs,
            nx=int(nx),
            ny=int(ny),
            cycle_s=int(cycle_s),
            sat_cadence_s=int(sat_cadence_s),
            dx_m=dx_m,
            dx_deg=dx_deg,
            upper_left_xy_m=upper_left_xy_m,
            upper_left_lonlat=upper_left_lonlat,
        )


@dataclass(frozen=True)
class ChannelConfig:
    group: str
    name: str
    units: str | None
    dtype: str
    scale: float
    source: str
    resampling: str
    fill_value: int | float

    @property
    def qualified_name(self) -> str:
        return f"{self.group}/{self.name}"

    @classmethod
    def from_mapping(cls, group: str, name: str, raw: Mapping[str, Any]) -> "ChannelConfig":
        required = {"dtype", "scale", "source", "resampling", "fill_value"}
        missing = required - raw.keys()
        if missing:
            raise ValueError(f"{group}/{name} missing fields: {sorted(missing)}")
        return cls(
            group=group,
            name=name,
            units=None if raw.get("units") is None else str(raw["units"]),
            dtype=str(raw["dtype"]),
            scale=float(raw["scale"]),
            source=str(raw["source"]),
            resampling=str(raw["resampling"]),
            fill_value=raw["fill_value"],
        )


def load_domains(path: str | Path | None = None) -> dict[str, DomainConfig]:
    raw = _read_yaml(Path(path) if path else CONFIG_DIR / "domains.yaml")
    entries = raw.get("domains")
    if not isinstance(entries, Mapping) or not entries:
        raise ValueError("domains.yaml must contain a non-empty domains mapping")
    return {
        str(name): DomainConfig.from_mapping(str(name), value) for name, value in entries.items()
    }


def load_domain(name: str, path: str | Path | None = None) -> DomainConfig:
    try:
        return load_domains(path)[name]
    except KeyError as exc:
        raise KeyError(f"unknown domain: {name}") from exc


def load_channels(path: str | Path | None = None) -> dict[str, ChannelConfig]:
    raw = _read_yaml(Path(path) if path else CONFIG_DIR / "channels.yaml")
    version = raw.get("channel_version")
    if not isinstance(version, int) or version <= 0:
        raise ValueError("channels.yaml channel_version must be a positive integer")
    entries = raw.get("channels")
    if not isinstance(entries, Mapping) or not entries:
        raise ValueError("channels.yaml must contain a non-empty channels mapping")
    result: dict[str, ChannelConfig] = {}
    for group, group_entries in entries.items():
        if not isinstance(group_entries, Mapping):
            raise ValueError(f"channel group {group} must be a mapping")
        for name, value in group_entries.items():
            channel = ChannelConfig.from_mapping(str(group), str(name), value)
            if channel.qualified_name in result:
                raise ValueError(f"duplicate channel {channel.qualified_name}")
            result[channel.qualified_name] = channel
    return result


def load_channel(name: str, path: str | Path | None = None) -> ChannelConfig:
    channels = load_channels(path)
    qualified = (
        name if "/" in name else next((key for key in channels if key.endswith(f"/{name}")), None)
    )
    if qualified is None or qualified not in channels:
        raise KeyError(f"unknown channel: {name}")
    return channels[qualified]
