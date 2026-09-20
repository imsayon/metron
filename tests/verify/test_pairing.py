from datetime import datetime, timedelta, timezone

from metron.verify import ForecastRecord, TruthRecord, pair_by_arrival_time

UTC = timezone.utc


def test_pairing_uses_observation_window_and_arrival_cutoff() -> None:
    issue = datetime(2026, 5, 3, 9, 30, tzinfo=UTC)
    forecasts = [ForecastRecord("f1", issue, 30, 0.7)]
    truths = [
        TruthRecord("late", issue + timedelta(minutes=10), issue + timedelta(minutes=40), True),
        TruthRecord("early", issue + timedelta(minutes=20), issue + timedelta(minutes=25), False),
    ]

    assert pair_by_arrival_time(forecasts, truths, as_of=issue + timedelta(minutes=20)) == ()
    pairs = pair_by_arrival_time(forecasts, truths, as_of=issue + timedelta(minutes=45))
    assert [pair.truth.truth_id for pair in pairs] == ["late"]


def test_pairing_is_order_independent_and_excludes_issue_time() -> None:
    issue = datetime(2026, 5, 3, 9, 30, tzinfo=UTC)
    forecast = ForecastRecord("f1", issue, 30)
    truths = [
        TruthRecord("at-issue", issue, issue, False),
        TruthRecord(
            "in-window",
            issue + timedelta(minutes=30),
            issue + timedelta(minutes=31),
            True,
        ),
    ]

    pairs = pair_by_arrival_time([forecast], list(reversed(truths)))
    assert [pair.truth.truth_id for pair in pairs] == ["in-window"]
