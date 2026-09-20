import asyncio
from datetime import timedelta
from urllib.parse import quote

from metron.api import APIServer
from metron.products import fixture_product

VIEWER = {"Authorization": "Bearer viewer-token"}
FORECASTER = {"Authorization": "Bearer forecaster-token"}


def _api() -> APIServer:
    api = APIServer(
        token_roles={
            "viewer-token": "viewer",
            "forecaster-token": "forecaster",
            "admin-token": "admin",
        }
    )
    product = fixture_product()
    issue = product.provenance.issue_time
    api.add_product(
        product,
        arrivals=[
            {
                "track_id": "fixture-track",
                "target": {"target_id": "VECC", "name": "Kolkata (NSCBI)"},
                "p_arrival": 0.71,
                "t10_min": 35,
                "t50_min": 52,
                "t90_min": 80,
            }
        ],
    )
    api.manifests = [
        {
            "source": "sat",
            "object_key": "raw/sat/1",
            "obs_time": issue.isoformat(),
            "arrival_time": (issue + timedelta(seconds=1)).isoformat(),
            "sha256": "fixture-sha",
        }
    ]
    return api


def test_default_auth_does_not_ship_fixture_tokens() -> None:
    response = APIServer().handle("GET", "/v1/targets", {"Authorization": "Bearer viewer-token"})
    assert response.status == 401


def test_products_and_rfc7807_role_boundary() -> None:
    api = _api()
    listed = api.handle("GET", "/v1/products?domain=pilot_e", VIEWER)
    assert listed.status == 200
    assert listed.json["items"][0]["provenance"]["research"] is True

    forbidden = api.handle(
        "POST",
        "/v1/replay",
        VIEWER,
        {"domain": "pilot_e", "t_start": "2026-05-03T09:30:00Z", "t_end": "2026-05-03T10:30:00Z"},
    )
    assert forbidden.status == 403
    assert forbidden.headers["content-type"] == "application/problem+json"
    assert set(("type", "title", "status", "detail")) <= forbidden.json.keys()


def test_replay_targets_and_cap_approval_are_audited() -> None:
    api = _api()
    replay = api.handle(
        "POST",
        "/v1/replay",
        FORECASTER,
        {
            "domain": "pilot_e",
            "t_start": "2026-05-03T09:30:00Z",
            "t_end": "2026-05-03T10:30:00Z",
            "speed": 20,
        },
    )
    assert replay.status == 202
    assert replay.json["namespace"]["products"].startswith("products/replay/")

    custom = api.handle(
        "POST",
        "/v1/targets",
        FORECASTER,
        {
            "target_id": "TEST",
            "kind": "hospital",
            "name": "Test",
            "latitude": 22.5,
            "longitude": 88.3,
        },
    )
    assert custom.status == 201
    assert api.handle("DELETE", "/v1/targets/VECC", FORECASTER).status == 409

    issue = quote("2026-05-03T09:30:00Z", safe="")
    draft = api.handle(
        "POST",
        f"/v1/review/{issue}/draft-cap",
        FORECASTER,
        {
            "domain": "pilot_e",
            "hazards": ["lightning"],
            "targets": ["VECC"],
            "arrival": api.arrivals[("pilot_e", "2026-05-03T09:30:00Z")],
        },
    )
    assert draft.status == 201
    assert draft.json["status"] == "Test"
    assert draft.json["explanation"]["numbers_checked"] is True
    alert_id = draft.json["alert_id"]
    approved = api.handle(
        "POST", f"/v1/review/{alert_id}/approve", FORECASTER, {"notes": "reviewed"}
    )
    assert approved.status == 200
    assert approved.json["status"] == "Actual"
    assert approved.json["external_delivery"] == "disabled"
    assert [item["action"] for item in approved.json["audit"]] == ["draft", "approve"]


def test_target_get_is_available_to_viewer_and_openapi_is_published() -> None:
    api = _api()
    targets = api.handle("GET", "/v1/targets", VIEWER)
    assert targets.status == 200
    assert {item["target_id"] for item in targets.json["items"]} >= {"VECC", "KOLKATA-HQ"}
    assert "/v1/replay" in api.handle("GET", "/openapi.json").json["paths"]


def test_websocket_event_hub_delivers_product_updates() -> None:
    api = _api()

    async def read_event() -> dict:
        queue = api.hub.subscribe()
        api.hub.publish({"type": "status.changed", "rung": "R1"})
        return await asyncio.wait_for(queue.get(), timeout=0.1)

    assert asyncio.run(read_event()) == {"type": "status.changed", "rung": "R1"}


def test_asgi_preserves_non_json_cap_and_metric_bodies() -> None:
    api = _api()

    async def call(url: str) -> tuple[dict, bytes]:
        sent: list[dict] = []
        messages = iter([{"type": "http.request", "body": b"", "more_body": False}])

        async def receive() -> dict:
            return next(messages)

        async def send(message: dict) -> None:
            sent.append(message)

        await api(
            {"type": "http", "method": "GET", "path": url, "headers": [], "query_string": b""},
            receive,
            send,
        )
        return sent[0], sent[1]["body"]

    start, body = asyncio.run(call("/metrics"))
    assert start["headers"][0] == (b"content-type", b"text/plain; version=0.0.4")
    assert body == b"metron_products_issued_total 1\n"
