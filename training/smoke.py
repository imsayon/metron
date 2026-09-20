"""Small deterministic fixture smoke test; all fixture outputs are synthetic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
from metron.models.baselines import advect
from metron.models.calibration import CalibrationKey, CalibrationRegistry
from metron.models.data import AvailableFrame
from metron.models.m0 import M0Input, run_m0
from metron.models.m1_objects import (
    StormTracker,
    Target,
    compute_arrival_windows,
    detect_objects,
)
from metron.models.m2_ci_ltg import M2Input, apply_modality_dropout
from metron.models.m7_controller import ModalityStatus, choose_rung


def run_smoke() -> dict[str, object]:
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    field = np.zeros((24, 24), dtype=np.float32)
    field[8:12, 2:6] = 50
    frames = (
        AvailableFrame(field, start, start + timedelta(minutes=9), synthetic=True),
        AvailableFrame(
            field, start + timedelta(minutes=10), start + timedelta(minutes=10), synthetic=True
        ),
    )
    motion = np.zeros((2, 24, 24), dtype=np.float32)
    motion[0] = 1
    m0 = run_m0(
        M0Input(
            frames=frames,
            issue_time=start + timedelta(minutes=10),
            motion_uv=motion,
            motion_quality=1.0,
            coverage_fraction=1.0,
        )
    )
    assert m0.members.shape == (24, 36, 24, 24)
    assert m0.research_only and m0.backend == "numpy_fallback"

    tracker = StormTracker()
    first = tracker.update(detect_objects(field, threshold=35, min_area=8))
    second_field = advect(field, motion, 1)
    second = tracker.update(
        detect_objects(second_field, threshold=35, min_area=8), motion_uv=motion
    )
    assert len(first) == len(second) == 1
    arrival = compute_arrival_windows(
        second[0],
        [Target("target-1", x=12, y=9, radius_km=2)],
        np.repeat(motion[None, ...], 24, axis=0),
        horizon_steps=12,
    )[0]
    assert arrival.p_arrival == 1.0

    dropped = apply_modality_dropout(
        M2Input(
            modalities={"sat": np.ones((2, 2)), "radar": np.ones((2, 2)), "ltg": np.ones((2, 2))},
            valid={"sat": True, "radar": True, "ltg": True},
        ),
        seed=0,
    )
    assert any(dropped.valid.values())
    assert choose_rung(ModalityStatus(True, 5, True, 5, 1.0, True, 2, 2, True)).rung == "R0"

    calibration = CalibrationRegistry().fit(
        CalibrationKey("ci", 30, "R0", "pre_monsoon"),
        [0.1, 0.2, 0.8, 0.9],
        [0, 0, 1, 1],
        model_version="m2-smoke",
        fitted_on_run_id="fixture",
        min_positive=2,
    )
    assert calibration is not None
    assert np.all(np.diff(calibration.predict([0.1, 0.5, 0.9])) >= 0)
    return {
        "m0_backend": m0.backend,
        "m0_research_only": m0.research_only,
        "arrival_probability": arrival.p_arrival,
        "arrival_window": [arrival.t10, arrival.t50, arrival.t90],
        "rung": "R0",
        "calibration_id": calibration.calibration_id,
    }


if __name__ == "__main__":
    print(run_smoke())
