"""A small Zarr v2 filesystem writer with atomic metadata updates.

The implementation uses uncompressed v2 chunks so tests do not require the
optional zarr package. A full deployment can read the resulting layout with a
standard Zarr client and add a compressor at the storage boundary.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

import numpy as np

from .config import ChannelConfig, DomainConfig

try:
    import fcntl
except ImportError:  # pragma: no cover - Linux is the supported runtime.
    fcntl = None


GROUPS = ("sat", "radar", "ltg", "nwp", "static", "prov")
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
_IMMUTABLE_ATTRS = (
    "domain",
    "domain_version",
    "crs_wkt",
    "geotransform",
    "cycle_s",
    "channel_version",
)


class MetadataError(ValueError):
    pass


def _json_safe(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def build_metadata(domain: DomainConfig, *, channel_version: int) -> dict[str, Any]:
    return {
        "domain": domain.name,
        "domain_version": domain.version,
        "crs_wkt": domain.crs_wkt,
        "geotransform": list(domain.geotransform),
        "cycle_s": domain.cycle_s,
        "channel_version": channel_version,
        "shape": list(domain.shape),
        "y_orientation": "north_to_south",
    }


@contextmanager
def _metadata_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        _json_safe(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    with tempfile.NamedTemporaryFile(
        "wb", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        temp = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


class ZarrGridStore:
    """Create and update one versioned daily grid store."""

    def __init__(self, path: str | Path, domain: DomainConfig):
        self.path = Path(path)
        self.domain = domain
        self._lock_path = self.path / ".metadata.lock"

    @property
    def attrs_path(self) -> Path:
        return self.path / ".zattrs"

    def create(self, *, channel_version: int, extra_attrs: Mapping[str, Any] | None = None) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        for group in GROUPS:
            (self.path / group).mkdir(exist_ok=True)
        _atomic_json(self.path / ".zgroup", {"zarr_format": 2})
        metadata = build_metadata(self.domain, channel_version=channel_version)
        metadata.update(extra_attrs or {})
        self.write_metadata(metadata)

    def read_metadata(self) -> dict[str, Any]:
        if not self.attrs_path.exists():
            raise MetadataError(f"missing metadata: {self.attrs_path}")
        try:
            value = json.loads(self.attrs_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MetadataError(f"invalid metadata: {self.attrs_path}") from exc
        if not isinstance(value, dict):
            raise MetadataError(".zattrs must contain a JSON object")
        self._validate_required(value)
        return value

    def write_metadata(self, metadata: Mapping[str, Any]) -> None:
        candidate = dict(metadata)
        self._validate_required(candidate)
        with _metadata_lock(self._lock_path):
            if self.attrs_path.exists():
                current = self.read_metadata()
                for field in _IMMUTABLE_ATTRS:
                    if current.get(field) != candidate.get(field):
                        raise MetadataError(f"immutable metadata field changed: {field}")
                merged = {**current, **candidate}
            else:
                merged = candidate
            _atomic_json(self.attrs_path, merged)
            self.consolidate_metadata(_locked=True)

    def _validate_required(self, metadata: Mapping[str, Any]) -> None:
        missing = set(_IMMUTABLE_ATTRS) - metadata.keys()
        if missing:
            raise MetadataError(f"missing required metadata: {sorted(missing)}")
        if (
            metadata["domain"] != self.domain.name
            or metadata["domain_version"] != self.domain.version
        ):
            raise MetadataError("metadata domain does not match store domain")
        transform = metadata["geotransform"]
        if not isinstance(transform, Sequence) or len(transform) != 6:
            raise MetadataError("geotransform must contain six values")
        if any(isinstance(value, float) and not np.isfinite(value) for value in transform):
            raise MetadataError("geotransform contains a non-finite value")
        if not isinstance(metadata["channel_version"], int) or metadata["channel_version"] <= 0:
            raise MetadataError("channel_version must be a positive integer")

    def _array_dir(self, group: str, name: str) -> Path:
        if group not in ("", *GROUPS) or not _SAFE_NAME.fullmatch(name):
            raise ValueError(f"unsafe Zarr array path: {group}/{name}")
        return self.path / name if group == "" else self.path / group / name

    def initialize_layout(
        self,
        channels: Mapping[str, ChannelConfig],
        *,
        channel_version: int,
        time_length: int | None = None,
    ) -> None:
        """Create the locked daily layout from the channel catalogue."""

        self.create(channel_version=channel_version)
        length = time_length or 86_400 // self.domain.cycle_s
        if length <= 0:
            raise ValueError("time_length must be positive")
        self.ensure_array("", "time", shape=(length,), dtype="<i8", chunks=(length,), fill_value=0)
        for qualified_name, channel in channels.items():
            if qualified_name != channel.qualified_name:
                raise MetadataError(f"channel key does not match config: {qualified_name}")
            shape = (
                (self.domain.ny, self.domain.nx)
                if channel.group == "static"
                else (length, self.domain.ny, self.domain.nx)
            )
            chunks = tuple(min(256, size) for size in shape)
            if channel.group != "static":
                chunks = (1, chunks[1], chunks[2])
            self.ensure_array(
                channel.group,
                channel.name,
                shape=shape,
                dtype=channel.dtype,
                chunks=chunks,
                fill_value=channel.fill_value,
                attrs={
                    "channel": qualified_name,
                    "units": channel.units,
                    "scale": channel.scale,
                    "source": channel.source,
                    "resampling": channel.resampling,
                },
            )
        self.ensure_array(
            "prov", "source_bins", shape=(length,), dtype="<U1024", chunks=(1,), fill_value=""
        )

    def ensure_array(
        self,
        group: str,
        name: str,
        *,
        shape: Sequence[int],
        dtype: str,
        chunks: Sequence[int] | None = None,
        fill_value: int | float = 0,
        attrs: Mapping[str, Any] | None = None,
    ) -> Path:
        array_dir = self._array_dir(group, name)
        shape_tuple = tuple(int(value) for value in shape)
        chunk_tuple = tuple(int(value) for value in (chunks or shape_tuple))
        if (
            not shape_tuple
            or len(shape_tuple) != len(chunk_tuple)
            or any(value <= 0 for value in shape_tuple + chunk_tuple)
        ):
            raise ValueError("shape and chunks must be positive and have equal rank")
        array_dir.mkdir(parents=True, exist_ok=True)
        metadata = {
            "zarr_format": 2,
            "shape": list(shape_tuple),
            "chunks": list(chunk_tuple),
            "dtype": np.dtype(dtype).str,
            "compressor": None,
            "fill_value": fill_value,
            "order": "C",
            "filters": None,
        }
        with _metadata_lock(self._lock_path):
            metadata_path = array_dir / ".zarray"
            if metadata_path.exists():
                current = json.loads(metadata_path.read_text(encoding="utf-8"))
                for field in ("shape", "chunks", "dtype", "fill_value"):
                    if current.get(field) != metadata[field]:
                        raise MetadataError(
                            f"immutable array metadata field changed: {group}/{name}/{field}"
                        )
            else:
                _atomic_json(metadata_path, metadata)
            if attrs:
                attrs_path = array_dir / ".zattrs"
                current_attrs = (
                    json.loads(attrs_path.read_text(encoding="utf-8"))
                    if attrs_path.exists()
                    else {}
                )
                _atomic_json(attrs_path, {**current_attrs, **attrs})
            self.consolidate_metadata(_locked=True)
        return array_dir

    def write_slice(self, group: str, name: str, time_index: int, values: np.ndarray) -> None:
        """Write one complete 2-D time slice as uncompressed Zarr chunks."""

        array_dir = self._array_dir(group, name)
        metadata_path = array_dir / ".zarray"
        if not metadata_path.exists():
            raise MetadataError(f"array metadata does not exist: {group}/{name}")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        shape = tuple(metadata["shape"])
        chunks = tuple(metadata["chunks"])
        if len(shape) != 3 or len(chunks) != 3 or not 0 <= time_index < shape[0]:
            raise ValueError("write_slice requires a 3-D time array and valid time_index")
        array = np.asarray(values, dtype=np.dtype(metadata["dtype"]))
        if array.shape != shape[1:]:
            raise ValueError(f"expected slice shape {shape[1:]}, got {array.shape}")
        fill = np.asarray(metadata["fill_value"], dtype=array.dtype).item()
        with _metadata_lock(self._lock_path):
            for y_chunk, y0 in enumerate(range(0, shape[1], chunks[1])):
                for x_chunk, x0 in enumerate(range(0, shape[2], chunks[2])):
                    block = np.full((chunks[1], chunks[2]), fill, dtype=array.dtype)
                    source = array[
                        y0 : min(y0 + chunks[1], shape[1]), x0 : min(x0 + chunks[2], shape[2])
                    ]
                    block[: source.shape[0], : source.shape[1]] = source
                    path = array_dir / f"{time_index}.{y_chunk}.{x_chunk}"
                    self._atomic_bytes(path, block.tobytes(order="C"))
            self.consolidate_metadata(_locked=True)

    @staticmethod
    def _atomic_bytes(path: Path, payload: bytes) -> None:
        with tempfile.NamedTemporaryFile(
            "wb", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            temp = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)

    def consolidate_metadata(self, *, _locked: bool = False) -> None:
        def write() -> None:
            metadata: dict[str, Any] = {}
            for path in self.path.rglob(".*"):
                if path.name not in {".zgroup", ".zattrs", ".zarray"}:
                    continue
                relative = path.relative_to(self.path).as_posix()
                metadata[relative] = json.loads(path.read_text(encoding="utf-8"))
            for path in self.path.rglob(".zarray"):
                relative = path.relative_to(self.path).as_posix()
                metadata[relative] = json.loads(path.read_text(encoding="utf-8"))
            _atomic_json(
                self.path / ".zmetadata", {"zarr_consolidated_format": 1, "metadata": metadata}
            )

        if _locked:
            write()
        else:
            with _metadata_lock(self._lock_path):
                write()
