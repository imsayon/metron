import unittest
from datetime import datetime, timezone

from metron.labels import LabelCatalogue, LabelEvidence, LabelEvent, LabelValidationError


def event(**overrides):
    values = {
        "event_id": "hail-001",
        "hazard": "hail",
        "obs_time": datetime(2026, 5, 1, 12, tzinfo=timezone.utc),
        "latitude": 22.57,
        "longitude": 88.36,
        "source": "curated-report",
        "grade": "B",
        "evidence": (
            LabelEvidence(source="IMD", locator="report-1"),
        ),
        "location_error_km": 5,
        "time_error_min": 30,
    }
    values.update(overrides)
    return LabelEvent(**values)


class LabelCatalogueTests(unittest.TestCase):
    def test_add_and_grade(self):
        catalogue = LabelCatalogue()
        catalogue.add(event(
            evidence=(LabelEvidence(source="radar", locator="case-1", instrument_confirmed=True),),
        ))
        graded = catalogue.grade("hail-001", "A", location_error_km=None, time_error_min=None)
        self.assertEqual(graded.grade, "A")

    def test_grade_a_requires_instrument_evidence(self):
        with self.assertRaises(LabelValidationError):
            event(grade="A").validate()

    def test_version_proxy_and_synthetic_state_are_explicit(self):
        item = event(
            event_id="cloudburst-001",
            hazard="cloudburst_area_proxy",
            grade="C",
            proxy=True,
            synthetic=True,
        ).validate()
        self.assertTrue(item.research_only)
        with self.assertRaises(LabelValidationError):
            event(definition_version="2").validate()


if __name__ == "__main__":
    unittest.main()
