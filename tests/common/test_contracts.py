from datetime import datetime, timedelta, timezone

import pytest
from metron.common import Abstention, InputProvenance, ProductSummary, Provenance, Rung, Tier

UTC = timezone.utc


def provenance() -> Provenance:
    issue = datetime(2026, 5, 3, 9, 30, tzinfo=UTC)
    return Provenance(
        domain="pilot_e",
        domain_version=1,
        issue_time=issue,
        valid_time=issue + timedelta(minutes=30),
        lead_min=30,
        tier=Tier.A,
        rung=Rung.R1,
        model_version="M2-test",
        skill_ref="F-M2-CSI-lead-pilot_e-2026pre",
        inputs=(InputProvenance("insat_browse", issue - timedelta(minutes=15), 15, False),),
        abstentions=(Abstention("M5", "no_velocity"),),
    )


def test_contracts_serialize_utc_and_explicit_abstention() -> None:
    product = ProductSummary("ltg_prob", "p_flash_8km", 30, "probability", provenance())

    payload = product.to_dict()

    assert payload["provenance"]["issue_time"] == "2026-05-03T09:30:00Z"
    assert payload["provenance"]["abstentions"] == [{"module": "M5", "reason_code": "no_velocity"}]
    assert payload["provenance"]["inputs"][0]["calibrated"] is False


def test_contracts_reject_naive_time_and_unknown_reason() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Provenance(
            domain="pilot_e",
            domain_version=1,
            issue_time=datetime(2026, 1, 1),
            valid_time=datetime(2026, 1, 1),
            lead_min=0,
            tier="A",
            rung="R0",
            model_version="test",
        )

    with pytest.raises(ValueError, match="unknown abstention"):
        Abstention("M2", "made_up_reason")
