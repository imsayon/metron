import unittest

import numpy as np

from metron.models.availability import DatasetAvailability, TrainingUnavailable
from metron.models.calibration import CalibrationKey, CalibrationRegistry
from metron.models.m2_ci_ltg import M2Input, apply_modality_dropout
from metron.models.m3_blend import blend
from metron.models.m4_hail import HailFeatures, hail_signature
from metron.models.m5_downburst import DownburstFeatures, downburst_score
from metron.models.m7_controller import ModalityStatus, choose_rung
from training.gates import SplitValidationError, validate_split


class DegradationTests(unittest.TestCase):
    def test_controller_selects_rungs_and_abstains(self):
        r0 = choose_rung(ModalityStatus(True, 1, True, 1, 0.5, True, 1, 2, True))
        self.assertEqual(r0.rung, "R0")
        r2 = choose_rung(ModalityStatus(True, 1, False, 100, 0, False, 100, 0, True))
        self.assertEqual(r2.rung, "R2")
        r4 = choose_rung(ModalityStatus(False, 100, False, 100, 0, False, 100, 0, False))
        self.assertEqual(r4.rung, "R4")

    def test_modality_dropout_never_drops_all_valid_stems(self):
        value = M2Input(
            {"sat": np.ones((2, 2)), "radar": np.ones((2, 2))},
            {"sat": True, "radar": True},
        )
        result = apply_modality_dropout(value, seed=2, probabilities={"sat": 1, "radar": 1})
        self.assertTrue(any(result.valid.values()))

    def test_missing_nwp_and_radar_are_explicit(self):
        nowcast = np.ones((2, 3, 2, 2))
        self.assertEqual(blend(nowcast, None).abstentions[0].reason_code, "nwp_missing")
        self.assertEqual(
            hail_signature(HailFeatures(radar_valid=False)).abstentions[0].reason_code,
            "no_radar",
        )
        self.assertEqual(
            downburst_score(DownburstFeatures(1, 1, 1, 1, 1, False)).abstentions[0].reason_code,
            "no_velocity",
        )

    def test_calibration_requires_data_and_supports_fallback(self):
        registry = CalibrationRegistry()
        key = CalibrationKey("ci", 30, "R0", "all")
        table = registry.fit(
            key,
            [0.1, 0.2, 0.8, 0.9],
            [0, 0, 1, 1],
            model_version="m2",
            fitted_on_run_id="run-1",
            min_positive=2,
        )
        self.assertIsNotNone(table)
        fallback = registry.fit(
            CalibrationKey("ci", 30, "R0", "monsoon"),
            [0.4],
            [1],
            model_version="m2",
            fitted_on_run_id="run-2",
            min_positive=2,
        )
        self.assertEqual(fallback.fallback_from.season, "monsoon")
        self.assertEqual(fallback.calibration_id, table.calibration_id)

    def test_training_and_split_gates_refuse_unavailable_claims(self):
        with self.assertRaises(TrainingUnavailable):
            DatasetAvailability("fixture", synthetic=True).require_training("M2")
        with self.assertRaises(SplitValidationError):
            validate_split("random_frames")
        self.assertEqual(validate_split("chronological"), "chronological")
