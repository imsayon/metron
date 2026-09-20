from datetime import datetime, timedelta, timezone

import numpy as np

from metron.qc.lightning import qc_lightning, validate_lightning_rows
from metron.qc.nwp import qc_nwp
from metron.qc.radar import qc_radar
from metron.qc.satellite import qc_satellite


UTC = timezone.utc
OBS = datetime(2026, 9, 21, 10, tzinfo=UTC)
ARRIVAL = OBS + timedelta(minutes=2)
ISSUE = OBS + timedelta(minutes=5)


def test_satellite_qc_rejects_physical_and_nonfinite_values():
    result = qc_satellite(
        "ir1",
        np.array([[220.0, 900.0, np.nan]], dtype=np.float32),
        obs_time=OBS,
        arrival_time=ARRIVAL,
        issue_time=ISSUE,
    )
    assert result.valid_mask.tolist() == [[1, 0, 0]]
    assert np.isfinite(result.values).all()
    assert "uncalibrated" in result.flags
    assert result.age_min == 5.0


def test_radar_velocity_boundary_abstains_without_verified_velocity():
    result = qc_radar(
        "div_lowlvl",
        np.ones((2, 2), dtype=np.float32) * 0.01,
        obs_time=OBS,
        arrival_time=ARRIVAL,
        issue_time=ISSUE,
        has_velocity=False,
    )
    assert result.missing
    assert result.missing_reason == "no_velocity"
    assert not result.valid_mask.any()


def test_lightning_access_gate_is_explicit_and_rows_have_a_schema():
    result = qc_lightning(
        "dens_15",
        np.ones((2, 2), dtype=np.float32),
        obs_time=OBS,
        arrival_time=ARRIVAL,
        issue_time=ISSUE,
        source_access_verified=False,
    )
    assert result.missing_reason == "ltg_unavailable"
    rows = validate_lightning_rows([{"time_utc": OBS.isoformat(), "lat": 22.0, "lon": 88.0, "type": "CG"}])
    assert len(rows) == 1


def test_nwp_qc_refuses_data_that_arrived_after_issue_time():
    result = qc_nwp(
        "cape",
        np.ones((2, 2), dtype=np.float32),
        obs_time=OBS,
        arrival_time=ISSUE + timedelta(seconds=1),
        issue_time=ISSUE,
        cycle_used="2026092106",
        shape=(2, 2),
    )
    assert result.missing
    assert result.missing_reason == "nwp_not_arrived"
