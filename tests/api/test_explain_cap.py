from datetime import datetime, timezone

from metron.api.cap import CAP_NS, CAPComposer
from metron.api.explain import ExplanationService, check_explanation


def test_explanation_rejects_mismatched_numbers_and_hazards() -> None:
    payload = {
        "hazards": ["lightning"],
        "target": {"name": "VECC"},
        "arrival": [{"p_arrival": 0.71, "t10_min": 35, "t50_min": 52, "t90_min": 80}],
        "provenance": {"watermark": "EXPERIMENTAL GUIDANCE — NOT AN OFFICIAL IMD WARNING"},
    }
    valid = ExplanationService().generate(payload, audience="public")
    assert valid.numbers_checked is True
    assert check_explanation(valid.text, payload, "public")[0] is True
    assert check_explanation(valid.text.replace("0.71", "0.91"), payload)[0] is False
    assert check_explanation(valid.text + " hail", payload)[0] is False


def test_cap_starts_in_test_mode_and_contains_experimental_sender() -> None:
    xml = CAPComposer().compose(
        alert_id="metron-pilot_e-1",
        domain="pilot_e",
        issue_time=datetime(2026, 5, 3, tzinfo=timezone.utc),
        hazards=["lightning"],
        targets=[{"target_id": "VECC", "name": "Kolkata (NSCBI)"}],
        probability=0.71,
        t10_min=35,
        t90_min=80,
    )
    assert f'xmlns="{CAP_NS}"' in xml
    assert "<status>Test</status>" in xml
    assert "not an official IMD warning" in xml
