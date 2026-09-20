import unittest
from datetime import datetime, timedelta, timezone

import numpy as np

from metron.models.baselines import advect, lagrangian_persistence
from metron.models.data import AvailableFrame, DataAvailabilityError, select_available_frames
from metron.models.m0 import M0Config, M0Input, run_m0


class BaselineTests(unittest.TestCase):
    def test_advection_does_not_wrap_at_boundary(self):
        field = np.zeros((3, 4), dtype=np.float32)
        field[1, 0] = 1
        motion = np.zeros((2, 3, 4), dtype=np.float32)
        motion[0] = 1
        moved = advect(field, motion)
        self.assertEqual(moved[1, 1], 1)
        self.assertEqual(moved[1, 0], 0)

    def test_issue_time_excludes_late_frame(self):
        now = datetime(2026, 5, 1, tzinfo=timezone.utc)
        frames = (
            AvailableFrame(np.ones((2, 2)), now, now),
            AvailableFrame(np.ones((2, 2)) * 2, now + timedelta(minutes=10), now + timedelta(minutes=11)),
        )
        selected = select_available_frames(frames, issue_time=now, count=1)
        self.assertEqual(float(selected[0].values[0, 0]), 1)
        with self.assertRaises(DataAvailabilityError):
            select_available_frames(frames, issue_time=now, count=2)

    def test_m0_is_seed_deterministic_and_falls_back_for_poor_motion(self):
        now = datetime(2026, 5, 1, tzinfo=timezone.utc)
        field = np.ones((4, 4), dtype=np.float32)
        frame = AvailableFrame(field, now, now, synthetic=True)
        value = M0Input((frame,), now, np.zeros((2, 4, 4)), 1, 1)
        first = run_m0(value, M0Config(horizon_steps=2, members=3, seed=7))
        second = run_m0(value, M0Config(horizon_steps=2, members=3, seed=7))
        np.testing.assert_array_equal(first.members, second.members)
        fallback = run_m0(
            M0Input((frame,), now, np.zeros((2, 4, 4)), 0.1, 1),
            M0Config(horizon_steps=2, members=3),
        )
        self.assertEqual(fallback.backend, "persistence_fallback")
        self.assertEqual(fallback.abstentions[0].reason_code, "poor_motion")

    def test_lagrangian_output_has_one_frame_per_step(self):
        field = np.eye(4, dtype=np.float32)
        motion = np.zeros((2, 4, 4), dtype=np.float32)
        self.assertEqual(lagrangian_persistence(field, motion, 3).shape, (3, 4, 4))
