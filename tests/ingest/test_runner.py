from datetime import datetime, timezone

from metron.ingest import (
    HttpResponse,
    IngestRunner,
    InsatBrowseAdapter,
    ManifestStore,
    RetryPolicy,
    SourceSpec,
    TransportError,
)


UTC = timezone.utc


class RetryingFakeClient:
    def __init__(self, response: HttpResponse, failures: int):
        self.response = response
        self.failures = failures
        self.calls = 0

    def get(self, url: str, *, headers=None, timeout_s=30.0) -> HttpResponse:
        self.calls += 1
        if self.calls <= self.failures:
            raise TransportError("temporary source outage")
        return self.response


def source_spec() -> SourceSpec:
    return SourceSpec(
        name="insat_browse",
        access_class="VIEW",
        cadence_s=300,
        expected_latency_s=1200,
        endpoint="https://example.test/{product}",
        auth="none",
        parser="fixture",
        obs_time_rule="header",
        retention_days=30,
    )


def test_runner_retries_transport_failure_and_writes_one_manifest(tmp_path) -> None:
    url = "https://example.test/3SIMG_fixture.jpg"
    body = b"\xff\xd8\xff METRON 21SEP2026 0000 UTC"
    response = HttpResponse(
        url=url,
        status=200,
        headers={"Content-Type": "image/jpeg"},
        body=body,
        received_at=datetime(2026, 9, 21, 0, 10, tzinfo=UTC),
    )
    fake = RetryingFakeClient(response, failures=2)
    adapter = InsatBrowseAdapter(
        source_spec(),
        [url],
        client=fake,
        retry_policy=RetryPolicy(attempts=3, backoff_s=0),
        sleep=lambda _: None,
    )

    with ManifestStore() as store:
        result = IngestRunner(store, archive_root=tmp_path / "archive").run_once(adapter)

        assert result.accepted_count == 1
        assert result.errors == ()
        assert fake.calls == 3
        assert store.count(source="insat_browse") == 1
        assert result.health.status == "healthy"
        assert result.manifests[0].path is not None


def test_runner_quarantines_untimed_payload_and_does_not_manifest_it(tmp_path) -> None:
    url = "https://example.test/3SIMG_fixture.jpg"
    response = HttpResponse(
        url=url,
        status=200,
        headers={"Content-Type": "image/jpeg"},
        body=b"\xff\xd8\xff no timestamp",
        received_at=datetime(2026, 9, 21, 0, 10, tzinfo=UTC),
    )

    class Client:
        def get(self, url: str, *, headers=None, timeout_s=30.0):
            return response

    adapter = InsatBrowseAdapter(source_spec(), [url], client=Client(), retry_policy=RetryPolicy(attempts=1))
    with ManifestStore() as store:
        result = IngestRunner(store, quarantine_root=tmp_path / "quarantine").run_once(adapter)

        assert result.accepted_count == 0
        assert len(result.quarantined) == 1
        assert result.quarantined[0].reason == "missing_source_timestamp"
        assert store.count() == 0
        assert list((tmp_path / "quarantine" / "insat_browse").glob("*.json"))
