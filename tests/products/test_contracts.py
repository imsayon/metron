from datetime import datetime, timedelta, timezone

import pytest
from metron.products import (
    ContractError,
    InputProvenance,
    MemoryCOGWriter,
    MemoryPostGISWriter,
    ProductWriter,
    Provenance,
    fixture_product,
    validate_product_summary,
)


def test_fixture_product_is_replay_badged_and_round_trips() -> None:
    product = fixture_product()
    assert product.provenance.mode == "replay"
    assert product.provenance.research is True
    assert validate_product_summary(product.to_dict()) == product


def test_live_product_without_skill_reference_is_rejected() -> None:
    issue = datetime(2026, 5, 3, tzinfo=timezone.utc)
    with pytest.raises(ContractError, match="skill_ref"):
        Provenance(
            domain="pilot_e",
            domain_version=1,
            issue_time=issue,
            valid_time=issue + timedelta(minutes=30),
            lead_min=30,
            tier="A",
            rung="R0",
            mode="live",
            model_version="m1",
            inputs=(InputProvenance("radar", issue, 0),),
        )


def test_product_writer_validates_before_cog_or_postgis_write() -> None:
    cog = MemoryCOGWriter()
    postgis = MemoryPostGISWriter()
    events: list[dict] = []

    class Events:
        def publish(self, event: dict) -> None:
            events.append(event)

    writer = ProductWriter(cog, postgis, Events())
    writer.write(fixture_product(), b"fixture")
    assert len(cog.objects) == len(postgis.rows) == len(events) == 1
    assert events[0]["type"] == "products.issued"
