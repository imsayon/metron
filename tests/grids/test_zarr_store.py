import json

import numpy as np
import pytest

from metron.grids.config import load_channels, load_domain
from metron.grids.zarr_store import MetadataError, ZarrGridStore


def test_zarr_metadata_is_atomic_and_domain_locked(tmp_path):
    store = ZarrGridStore(tmp_path / "grid.zarr", load_domain("pilot_e"))
    store.create(channel_version=1)
    metadata = store.read_metadata()
    assert metadata["domain"] == "pilot_e"
    assert metadata["domain_version"] == 1
    assert metadata["geotransform"] == [-500000.0, 2000.0, 0.0, 450000.0, 0.0, -2000.0]
    assert (tmp_path / "grid.zarr" / ".zmetadata").exists()

    with pytest.raises(MetadataError):
        store.write_metadata({**metadata, "domain_version": 2})


def test_zarr_time_slice_writes_uncompressed_v2_chunks(tmp_path):
    store = ZarrGridStore(tmp_path / "grid.zarr", load_domain("pilot_e"))
    store.create(channel_version=1)
    store.ensure_array("radar", "zmax", shape=(2, 3, 4), dtype="<f4", chunks=(1, 2, 2), fill_value=-32.0)
    with pytest.raises(MetadataError, match="immutable array metadata"):
        store.ensure_array("radar", "zmax", shape=(3, 3, 4), dtype="<f4", chunks=(1, 2, 2), fill_value=-32.0)
    store.write_slice("radar", "zmax", 0, np.arange(12, dtype=np.float32).reshape(3, 4))
    chunk = tmp_path / "grid.zarr" / "radar" / "zmax" / "0.1.1"
    assert chunk.exists()
    assert chunk.read_bytes()[:4] == np.array([10.0], dtype="<f4").tobytes()
    consolidated = json.loads((tmp_path / "grid.zarr" / ".zmetadata").read_text())
    assert "radar/zmax/.zarray" in consolidated["metadata"]


def test_zarr_layout_contains_time_channels_and_provenance(tmp_path):
    store = ZarrGridStore(tmp_path / "grid.zarr", load_domain("national_s"))
    store.initialize_layout(load_channels(), channel_version=1, time_length=2)
    root = tmp_path / "grid.zarr"
    assert (root / "time" / ".zarray").exists()
    assert (root / "sat" / "ir1" / ".zarray").exists()
    assert (root / "static" / "elevation" / ".zarray").exists()
    assert (root / "prov" / "source_bins" / ".zarray").exists()
