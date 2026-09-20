import base64
import json
from datetime import datetime, timezone
from pathlib import Path

from metron.ingest import (
    GFSAdapter,
    HttpResponse,
    ImdApiAdapter,
    ImdRadarProductAdapter,
    InsatBrowseAdapter,
    RetryPolicy,
    SourceSpec,
    decode_radar_palette,
    load_source_specs,
    parse_nowcast_categories,
)

UTC = timezone.utc
FIXTURES = Path(__file__).parents[2] / "fixtures" / "sources"


def fixture_bytes(name: str) -> bytes:
    return base64.b64decode((FIXTURES / name).read_text(encoding="ascii"))


class FakeClient:
    def __init__(self, response: HttpResponse):
        self.response = response
        self.calls: list[str] = []

    def get(self, url: str, *, headers=None, timeout_s=30.0) -> HttpResponse:
        self.calls.append(url)
        return self.response


def spec(name: str, endpoint: str, **settings) -> SourceSpec:
    return SourceSpec(
        name=name,
        access_class="VIEW",
        cadence_s=300,
        expected_latency_s=1200,
        endpoint=endpoint,
        auth="none",
        parser="fixture",
        obs_time_rule="fixture",
        retention_days=30,
        settings=settings,
    )


def response(url: str, body: bytes, content_type: str, minute: int = 20) -> HttpResponse:
    return HttpResponse(
        url=url,
        status=200,
        headers={"Content-Type": content_type},
        body=body,
        received_at=datetime(2026, 9, 21, 0, minute, tzinfo=UTC),
    )


def test_insat_browse_extracts_header_timestamp_and_marks_uncalibrated() -> None:
    url = "https://example.test/3SIMG_fixture.jpg"
    adapter = InsatBrowseAdapter(
        spec("insat_browse", url),
        [url],
        client=FakeClient(
            response(url, fixture_bytes("insat_browse.synthetic.jpg.b64"), "image/jpeg")
        ),
        retry_policy=RetryPolicy(attempts=1),
    )

    item = next(iter(adapter.poll()))

    assert item.station_or_sat == "INSAT-3DS"
    assert item.obs_time == datetime(2026, 9, 21, 0, tzinfo=UTC)
    assert item.metadata["calibrated"] is False
    assert item.metadata["obs_time_source"] == "header"


def test_radar_adapter_allows_estimated_time_when_overlay_is_not_textual() -> None:
    url = "https://example.test/Radar/caz_delhi.gif"
    body = b"GIF89a" + b"synthetic image without timestamp"
    adapter = ImdRadarProductAdapter(
        spec("imd_radar_products", "https://example.test/Radar/{product}_{station}.gif"),
        urls=[("delhi", "caz", url)],
        client=FakeClient(response(url, body, "image/gif")),
        retry_policy=RetryPolicy(attempts=1),
    )

    item = next(iter(adapter.poll()))

    assert item.metadata["obs_time_estimated"] is True
    assert item.metadata["channel"] == "zmax"
    assert item.obs_time == datetime(2026, 9, 21, 0, 15, tzinfo=UTC)


def test_radar_palette_decoder_reports_unknown_pixels() -> None:
    summary = decode_radar_palette(fixture_bytes("imd_radar.synthetic.gif.b64"), {0: 0.0, 1: 10.0})

    assert (summary.width, summary.height) == (4, 4)
    assert summary.known_pixels == 8
    assert summary.unknown_pixels == 8
    assert summary.histogram == {0.0: 4, 10.0: 4}


def test_gfs_adapter_separates_issue_and_valid_time() -> None:
    url = "https://example.test/gfs"
    cycle = datetime(2026, 9, 21, 0, tzinfo=UTC)
    adapter = GFSAdapter(
        spec("gfs", url),
        cycle=cycle,
        steps=[3],
        client=FakeClient(
            response(url, fixture_bytes("gfs.synthetic.grib2.b64"), "application/octet-stream")
        ),
        retry_policy=RetryPolicy(attempts=1),
    )

    item = next(iter(adapter.poll()))

    assert item.issue_time == cycle
    assert item.valid_time == datetime(2026, 9, 21, 3, tzinfo=UTC)
    assert item.obs_time == item.valid_time
    assert item.metadata["forecast"] is True
    assert "f003" in adapter.build_url(cycle, 3)


def test_imd_api_adapter_archives_payload_and_extracts_categories() -> None:
    url = "https://example.test/api"
    body = (FIXTURES / "imd_nowcast.synthetic.json").read_bytes()
    adapter = ImdApiAdapter(
        spec("imd_api_nowcast", url),
        kind="nowcast",
        client=FakeClient(response(url, body, "application/json", minute=10)),
        retry_policy=RetryPolicy(attempts=1),
    )

    item = next(iter(adapter.poll()))

    assert json.loads(item.payload) == json.loads(body)
    assert item.issue_time == datetime(2026, 9, 21, 0, tzinfo=UTC)
    assert item.valid_time == datetime(2026, 9, 21, 3, tzinfo=UTC)
    assert item.metadata["category_count"] == 1
    assert parse_nowcast_categories(json.loads(body))[0]["category"] == "Yellow"


def test_committed_source_manifests_are_loadable() -> None:
    specs = load_source_specs(Path(__file__).parents[2] / "configs" / "sources")

    assert set(specs) == {
        "gfs",
        "imd_api_aws",
        "imd_api_nowcast",
        "imd_radar_products",
        "insat_browse",
    }
    assert specs["insat_browse"].settings["calibrated"] is False
