import unittest

from training.smoke import run_smoke


class SmokeTests(unittest.TestCase):
    def test_deterministic_fixture_smoke(self):
        result = run_smoke()
        self.assertEqual(result["m0_backend"], "numpy_fallback")
        self.assertTrue(result["m0_research_only"])
        self.assertEqual(result["arrival_probability"], 1.0)
        self.assertEqual(result["rung"], "R0")
