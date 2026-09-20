import unittest

import numpy as np
from metron.models.baselines import advect
from metron.models.m1_objects import (
    EmpiricalSurvival,
    StormTracker,
    Target,
    compute_arrival_windows,
    detect_objects,
)


class ObjectTests(unittest.TestCase):
    def fixture_field(self):
        field = np.zeros((24, 24), dtype=np.float32)
        field[8:12, 2:6] = 50
        return field

    def test_detection_and_tracking_preserve_track_without_self_parent(self):
        field = self.fixture_field()
        motion = np.zeros((2, 24, 24), dtype=np.float32)
        motion[0] = 1
        tracker = StormTracker()
        first = tracker.update(detect_objects(field, threshold=35, min_area=8))
        second = tracker.update(
            detect_objects(advect(field, motion), threshold=35, min_area=8), motion_uv=motion
        )
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0].track_id, second[0].track_id)
        self.assertEqual(second[0].parent_track_ids, ())
        self.assertEqual(second[0].lifecycle_state, "Mature")

    def test_arrival_window_is_a_window_and_uses_survival(self):
        field = self.fixture_field()
        motion = np.zeros((2, 24, 24), dtype=np.float32)
        motion[0] = 1
        storm = StormTracker().update(detect_objects(field, threshold=35, min_area=8))[0]
        result = compute_arrival_windows(
            storm,
            [Target("hq", 12, 9, 2)],
            np.repeat(motion[None, ...], 4, axis=0),
            horizon_steps=12,
            survival=EmpiricalSurvival.fit([10, 20, 30]),
        )[0]
        self.assertEqual(result.p_arrival, 1)
        self.assertLessEqual(result.t10, result.t50)
        self.assertLessEqual(result.t50, result.t90)
        self.assertGreater(result.p_decay, 0)
