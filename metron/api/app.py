"""Small typed HTTP/ASGI API for the F4 product boundary.

The server is intentionally framework-free because this repository currently
has no runtime manifest.  It exposes a normal ASGI callable, so deployment can
bind it to an ASGI server later without changing route semantics.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from metron.products.contracts import (
    ContractError,
    ProductSummary,
    Target,
    validate_product_summary,
)
from metron.replay.controller import ReplayController, ReplayError

from .cap import CAPComposer
from .explain import ExplanationService

ROLE_LEVEL = {"viewer": 1, "forecaster": 2, "admin": 3}
MAX_REQUEST_BODY_BYTES = 1_048_576


class Problem(Exception):
    def __init__(
        self,
        status: int,
        title: str,
        detail: str,
        *,
        type: str = "about:blank",
        instance: str | None = None,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.title = title
        self.detail = detail
        self.type = type
        self.instance = instance

    def body(self) -> dict[str, Any]:
        result = {
            "type": self.type,
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
        }
        if self.instance:
            result["instance"] = self.instance
        return result


@dataclass(frozen=True)
class Principal:
    subject: str
    role: str


@dataclass(frozen=True)
class Response:
    status: int
    body: Any
    headers: Mapping[str, str] = field(default_factory=dict)

    @property
    def json(self) -> Any:
        return self.body


class EventHub:
    """In-process event fanout used by ProductWriter and WebSocket clients."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self._queues: set[asyncio.Queue[dict[str, Any]]] = set()

    def publish(self, event: Mapping[str, Any]) -> None:
        item = dict(event)
        self.events.append(item)
        for queue in tuple(self._queues):
            queue.put_nowait(item)

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._queues.discard(queue)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str).encode()


def _query(url: str) -> tuple[str, dict[str, str]]:
    parsed = urlsplit(url)
    return parsed.path, {
        key: values[-1] for key, values in parse_qs(parsed.query).items() if values
    }


def _datetime(value: str, name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Problem(400, "Invalid request", f"{name} must be ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise Problem(400, "Invalid request", f"{name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _integer(value: str, name: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise Problem(400, "Invalid request", f"{name} must be an integer") from exc


def _body(value: bytes | str | Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None or value == b"" or value == "":
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    try:
        parsed = json.loads(value.decode() if isinstance(value, bytes) else value)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise Problem(400, "Invalid JSON", "request body must contain valid JSON") from exc
    if not isinstance(parsed, dict):
        raise Problem(400, "Invalid JSON", "request body must be a JSON object")
    return parsed


class _Auth:
    def __init__(self, token_roles: Mapping[str, str | Principal] | None = None) -> None:
        configured = token_roles or {}
        self.tokens: dict[str, Principal] = {}
        for token, value in configured.items():
            principal = value if isinstance(value, Principal) else Principal(token, value)
            if principal.role not in ROLE_LEVEL:
                raise ValueError(f"unknown role: {principal.role}")
            self.tokens[token] = principal

    def authenticate(self, headers: Mapping[str, str]) -> Principal:
        raw = next((value for key, value in headers.items() if key.lower() == "authorization"), "")
        scheme, _, token = raw.partition(" ")
        principal = self.tokens.get(token) if scheme.lower() == "bearer" else None
        if principal is None:
            raise Problem(401, "Unauthorized", "a valid bearer token is required")
        return principal

    def require(self, headers: Mapping[str, str], role: str) -> Principal:
        principal = self.authenticate(headers)
        if ROLE_LEVEL[principal.role] < ROLE_LEVEL[role]:
            raise Problem(403, "Forbidden", f"{role} role is required")
        return principal


DEFAULT_TARGETS = (
    Target(
        target_id="VECC",
        kind="airport",
        name="Kolkata (NSCBI)",
        latitude=22.6547,
        longitude=88.4467,
        radius_km=15,
        is_default=True,
    ),
    Target(
        target_id="KOLKATA-HQ",
        kind="district_hq",
        name="Kolkata district HQ",
        latitude=22.5726,
        longitude=88.3639,
        radius_km=15,
        admin_code="191",
        is_default=True,
    ),
)


class APIServer:
    """F4 API with fixture-safe in-memory stores."""

    def __init__(
        self,
        *,
        products: list[ProductSummary] | None = None,
        manifests: list[Mapping[str, Any]] | None = None,
        token_roles: Mapping[str, str | Principal] | None = None,
        clock: Callable[[], datetime] = _now,
        seed_defaults: bool = True,
    ) -> None:
        self.auth = _Auth(token_roles)
        self.clock = clock
        self.hub = EventHub()
        self.products: list[ProductSummary] = [
            validate_product_summary(item) for item in products or []
        ]
        self.objects: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self.arrivals: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self.verification: list[dict[str, Any]] = []
        self.targets: dict[str, Target] = (
            {item.target_id: item for item in DEFAULT_TARGETS} if seed_defaults else {}
        )
        self.replay = ReplayController()
        self.manifests = list(manifests or [])
        self.cap = CAPComposer()
        self.explain = ExplanationService()
        self.alerts: dict[str, dict[str, Any]] = {}
        self.audit: list[dict[str, Any]] = []

    def add_product(
        self,
        product: ProductSummary,
        *,
        objects: list[dict[str, Any]] | None = None,
        arrivals: list[dict[str, Any]] | None = None,
    ) -> ProductSummary:
        product = validate_product_summary(product)
        self.products.append(product)
        key = (product.provenance.domain, _iso(product.provenance.issue_time))
        if objects is not None:
            self.objects[key] = list(objects)
        if arrivals is not None:
            self.arrivals[key] = list(arrivals)
        self.hub.publish(
            {
                "type": "products.issued",
                "domain": product.provenance.domain,
                "issue_time": _iso(product.provenance.issue_time),
                "product": product.product,
                "lead_min": product.lead_min,
                "rung": product.provenance.rung,
                "abstentions": [item.to_dict() for item in product.provenance.abstentions],
            }
        )
        return product

    def handle(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str] | None = None,
        body: bytes | str | Mapping[str, Any] | None = None,
    ) -> Response:
        headers = headers or {}
        path, query = _query(url)
        try:
            return self._route(method.upper(), path, query, headers, body)
        except Problem as exc:
            return Response(
                exc.status,
                exc.body(),
                {"content-type": "application/problem+json"},
            )
        except (ContractError, ReplayError, ValueError) as exc:
            problem = Problem(400, "Invalid request", str(exc), instance=path)
            return Response(
                problem.status,
                problem.body(),
                {"content-type": "application/problem+json"},
            )

    def _route(
        self,
        method: str,
        path: str,
        query: Mapping[str, str],
        headers: Mapping[str, str],
        raw_body: bytes | str | Mapping[str, Any] | None,
    ) -> Response:
        if path in {"/healthz", "/v1/healthz"} and method == "GET":
            return self._json_response(200, {"status": "ok"})
        if path in {"/openapi.json", "/v1/openapi.json"} and method == "GET":
            return self._json_response(200, self.openapi())
        if path in {"/metrics", "/v1/metrics"} and method == "GET":
            return Response(
                200,
                "metron_products_issued_total %d\n" % len(self.products),
                {"content-type": "text/plain; version=0.0.4"},
            )
        if not path.startswith("/v1"):
            raise Problem(404, "Not Found", "route does not exist", instance=path)
        route = path[3:] or "/"
        if route == "/ws":
            raise Problem(426, "Upgrade Required", "use a WebSocket connection")
        principal = self.auth.authenticate(headers)
        if route == "/status" and method == "GET":
            return self._json_response(200, self._status())
        if route == "/products" and method == "GET":
            return self._json_response(
                200,
                {
                    "items": [item.to_dict() for item in self._list_products(query)],
                    "next_cursor": None,
                },
            )
        if route.startswith("/products/") and method == "GET":
            product_name = unquote(route.split("/", 2)[2])
            return self._json_response(200, self._get_product(product_name, query))
        if route == "/objects" and method == "GET":
            return self._json_response(200, self._objects(query))
        if route == "/arrival" and method == "GET":
            return self._json_response(200, self._arrivals(query))
        if route == "/abstentions" and method == "GET":
            return self._json_response(200, self._abstentions(query))
        if route == "/verification" and method == "GET":
            return self._json_response(200, {"items": self.verification})
        if route.startswith("/verification/figures/") and method == "GET":
            raise Problem(404, "Not Found", "no frozen figure is available in this fixture")
        if route == "/replay" and method == "POST":
            self._require(principal, "forecaster")
            data = _body(raw_body)
            if not data.get("domain") or not data.get("t_start") or not data.get("t_end"):
                raise Problem(400, "Invalid request", "domain, t_start, and t_end are required")
            state = self.replay.start(
                domain=str(data["domain"]),
                t_start=data["t_start"],
                t_end=data["t_end"],
                speed=float(data.get("speed", 1)),
                manifests=self.manifests,
            )
            return self._json_response(202, state.to_dict())
        if route.startswith("/replay/"):
            replay_id = unquote(route.split("/", 2)[2])
            if method == "GET":
                self._require(principal, "viewer")
                return self._json_response(200, self.replay.get(replay_id).to_dict())
            if method == "DELETE":
                self._require(principal, "forecaster")
                self.replay.delete(replay_id)
                return Response(204, b"", {"content-type": "application/json"})
        if route.startswith("/review/") and route.endswith("/draft-cap") and method == "POST":
            self._require(principal, "forecaster")
            issue = unquote(route[len("/review/") : -len("/draft-cap")].strip("/"))
            return self._draft_cap(issue, principal, _body(raw_body))
        if route.startswith("/review/") and route.endswith("/approve") and method == "POST":
            self._require(principal, "forecaster")
            alert_id = unquote(route[len("/review/") : -len("/approve")].strip("/"))
            return self._approve(alert_id, principal, _body(raw_body))
        if route.startswith("/cap/") and method == "GET":
            self._require(principal, "viewer")
            alert = self.alerts.get(unquote(route.split("/", 2)[2]))
            if alert is None:
                raise Problem(404, "Not Found", "CAP alert does not exist")
            return Response(200, alert["xml"], {"content-type": "application/cap+xml"})
        if route.startswith("/explain/") and method == "GET":
            self._require(principal, "viewer")
            return self._explain(unquote(route.split("/", 2)[2]), query)
        if route == "/targets" and method == "GET":
            self._require(principal, "viewer")
            return self._json_response(
                200, {"items": [item.to_dict() for item in self.targets.values()]}
            )
        if route == "/targets" and method == "POST":
            self._require(principal, "forecaster")
            target = self._target(_body(raw_body))
            if target.target_id in self.targets:
                raise Problem(409, "Conflict", "target_id already exists")
            self.targets[target.target_id] = target
            return self._json_response(201, target.to_dict())
        if route.startswith("/targets/"):
            target_id = unquote(route.split("/", 2)[2])
            if method in {"PUT", "PATCH"}:
                self._require(principal, "forecaster")
                if target_id not in self.targets:
                    raise Problem(404, "Not Found", "target does not exist")
                target = self._target(_body(raw_body), target_id=target_id)
                self.targets[target_id] = target
                return self._json_response(200, target.to_dict())
            if method == "DELETE":
                self._require(principal, "forecaster")
                target = self.targets.get(target_id)
                if target is None:
                    raise Problem(404, "Not Found", "target does not exist")
                if target.is_default:
                    raise Problem(409, "Conflict", "default targets cannot be deleted")
                del self.targets[target_id]
                return Response(204, b"", {"content-type": "application/json"})
        raise Problem(404, "Not Found", "route does not exist", instance=path)

    def _require(self, principal: Principal, role: str) -> None:
        if ROLE_LEVEL[principal.role] < ROLE_LEVEL[role]:
            raise Problem(403, "Forbidden", f"{role} role is required")

    def _json_response(self, status: int, body: Any) -> Response:
        return Response(status, body, {"content-type": "application/json"})

    def _status(self) -> dict[str, Any]:
        domains: dict[str, dict[str, Any]] = {}
        for product in self.products:
            provenance = product.provenance
            domains[provenance.domain] = {
                "rung": provenance.rung,
                "last_issue": _iso(provenance.issue_time),
                "cycle_latency_s": None,
                "mode": provenance.mode,
                "research": provenance.research,
            }
        return {"sources": [], "domains": domains, "skill_by_rung": {}, "uptime": {}}

    def _list_products(self, query: Mapping[str, str]) -> list[ProductSummary]:
        since = _datetime(query["since"], "since") if query.get("since") else None
        until = _datetime(query["until"], "until") if query.get("until") else None
        return [
            item
            for item in self.products
            if (not query.get("domain") or item.provenance.domain == query["domain"])
            and (not query.get("product") or item.product == query["product"])
            and (not query.get("tier") or item.provenance.tier == query["tier"])
            and (since is None or item.provenance.issue_time >= since)
            and (until is None or item.provenance.issue_time <= until)
        ]

    def _get_product(self, product_name: str, query: Mapping[str, str]) -> dict[str, Any]:
        for required in ("domain", "issue_time", "lead"):
            if not query.get(required):
                raise Problem(400, "Invalid request", f"{required} is required")
        for item in self.products:
            if (
                item.product == product_name
                and item.provenance.domain == query.get("domain")
                and item.provenance.issue_time == _datetime(query["issue_time"], "issue_time")
                and item.lead_min == _integer(query["lead"], "lead")
                and (not query.get("variant") or item.variant == query["variant"])
            ):
                return item.to_dict()
        raise Problem(404, "Not Found", "product does not exist")

    def _issue_key(self, query: Mapping[str, str]) -> tuple[str, str]:
        if not query.get("domain") or not query.get("issue_time"):
            raise Problem(400, "Invalid request", "domain and issue_time are required")
        return query["domain"], _iso(_datetime(query["issue_time"], "issue_time"))

    def _objects(self, query: Mapping[str, str]) -> dict[str, Any]:
        return {
            "type": "FeatureCollection",
            "features": self.objects.get(self._issue_key(query), []),
        }

    def _arrivals(self, query: Mapping[str, str]) -> dict[str, Any]:
        values = self.arrivals.get(self._issue_key(query), [])
        if query.get("target"):
            values = [
                item
                for item in values
                if item.get("target", {}).get("target_id") == query["target"]
            ]
        return {"items": values}

    def _abstentions(self, query: Mapping[str, str]) -> dict[str, Any]:
        domain, issue = self._issue_key(query)
        rows = [
            item.to_dict()
            for product in self.products
            if product.provenance.domain == domain and _iso(product.provenance.issue_time) == issue
            for item in product.provenance.abstentions
        ]
        return {"items": rows}

    def _target(self, data: Mapping[str, Any], target_id: str | None = None) -> Target:
        geometry = data.get("geometry", {})
        coordinates = geometry.get("coordinates", []) if isinstance(geometry, Mapping) else []
        latitude = data.get("latitude")
        longitude = data.get("longitude")
        if (latitude is None or longitude is None) and len(coordinates) == 2:
            longitude, latitude = coordinates
        if target_id is None:
            target_id = data.get("target_id")
        if not target_id:
            raise Problem(400, "Invalid target", "target_id is required")
        try:
            return Target(
                target_id=str(target_id),
                kind=str(data["kind"]),
                name=str(data["name"]),
                latitude=float(latitude),
                longitude=float(longitude),
                radius_km=float(data.get("radius_km", 15)),
                admin_code=data.get("admin_code"),
                is_default=bool(data.get("is_default", False)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise Problem(400, "Invalid target", "target fields are invalid") from exc

    def _resolve_targets(self, values: list[Any]) -> list[dict[str, Any]]:
        resolved: list[dict[str, Any]] = []
        for value in values:
            target = self.targets.get(value) if isinstance(value, str) else None
            if (
                target is None
                and isinstance(value, Mapping)
                and value.get("target_id") in self.targets
            ):
                target = self.targets[value["target_id"]]
            if target is None:
                raise Problem(400, "Invalid target", f"unknown target: {value}")
            resolved.append(target.to_dict())
        return resolved

    def _draft_cap(self, issue: str, principal: Principal, data: Mapping[str, Any]) -> Response:
        domain = str(data.get("domain", ""))
        hazards = data.get("hazards", [])
        if not domain or not isinstance(hazards, list) or not hazards:
            raise Problem(400, "Invalid request", "domain and hazards are required")
        target_values = data.get("targets", [item.target_id for item in DEFAULT_TARGETS])
        targets = self._resolve_targets(target_values)
        issue_time = _datetime(issue, "issue")
        sequence = 1
        alert_id = f"metron-{domain}-{issue_time.strftime('%Y%m%dT%H%M%SZ')}-{sequence}"
        while alert_id in self.alerts:
            sequence += 1
            alert_id = f"metron-{domain}-{issue_time.strftime('%Y%m%dT%H%M%SZ')}-{sequence}"
        arrival = data.get("arrival", [])
        row = (
            arrival[0]
            if isinstance(arrival, list) and arrival
            else arrival
            if isinstance(arrival, Mapping)
            else {}
        )
        probability = float(data.get("probability", row.get("p_arrival", 0)))
        t10 = int(row["t10_min"]) if row.get("t10_min") is not None else None
        t90 = int(row["t90_min"]) if row.get("t90_min") is not None else None
        cap_payload = self.cap.compose(
            alert_id=alert_id,
            domain=domain,
            issue_time=issue_time,
            hazards=hazards,
            targets=targets,
            probability=probability,
            t10_min=t10,
            t90_min=t90,
            status="Test",
        )
        payload = {
            "hazards": hazards,
            "arrival": arrival,
            "target": targets[0] if targets else {},
            "provenance": {"watermark": "EXPERIMENTAL GUIDANCE — NOT AN OFFICIAL IMD WARNING"},
        }
        explanation = self.explain.generate(
            payload, language=str(data.get("language", "en")), audience="forecaster"
        )
        self.alerts[alert_id] = {
            "alert_id": alert_id,
            "status": "Test",
            "xml": cap_payload,
            "domain": domain,
            "issue_time": issue_time,
            "hazards": hazards,
            "targets": targets,
            "probability": probability,
            "t10_min": t10,
            "t90_min": t90,
            "audit": [],
        }
        self._record_audit(alert_id, "draft", principal, {})
        return self._json_response(
            201,
            {
                "alert_id": alert_id,
                "status": "Test",
                "cap_xml": cap_payload,
                "explanation": explanation.to_dict(),
            },
        )

    def _approve(self, alert_id: str, principal: Principal, data: Mapping[str, Any]) -> Response:
        alert = self.alerts.get(alert_id)
        if alert is None:
            raise Problem(404, "Not Found", "CAP alert does not exist")
        if alert["status"] != "Test":
            raise Problem(409, "Conflict", "CAP alert has already been approved")
        alert["status"] = "Actual"
        alert["xml"] = self.cap.compose(
            alert_id=alert_id,
            domain=alert["domain"],
            issue_time=alert["issue_time"],
            hazards=alert["hazards"],
            targets=alert["targets"],
            probability=alert["probability"],
            t10_min=alert["t10_min"],
            t90_min=alert["t90_min"],
            status="Actual",
            approved_by=principal.subject,
        )
        self._record_audit(alert_id, "approve", principal, {"notes": data.get("notes", "")})
        return self._json_response(
            200,
            {
                "status": "Actual",
                "delivered_to": [],
                "receipt": None,
                "external_delivery": "disabled",
                "audit": alert["audit"],
            },
        )

    def _record_audit(
        self, alert_id: str, action: str, principal: Principal, details: Mapping[str, Any]
    ) -> None:
        item = {
            "action": action,
            "actor": principal.subject,
            "role": principal.role,
            "at": _iso(self.clock()),
            "details": dict(details),
        }
        self.alerts[alert_id]["audit"].append(item)
        self.audit.append({"alert_id": alert_id, **item})

    def _explain(self, issue: str, query: Mapping[str, str]) -> Response:
        domain = query.get("domain")
        if not domain:
            raise Problem(400, "Invalid request", "domain is required")
        issue_time = _datetime(issue, "issue")
        product = next(
            (
                item
                for item in self.products
                if item.provenance.domain == domain and item.provenance.issue_time == issue_time
            ),
            None,
        )
        if product is None:
            raise Problem(404, "Not Found", "product does not exist")
        key = (domain, _iso(issue_time))
        arrivals = self.arrivals.get(key, [])
        payload = {
            "product": product.product,
            "hazards": [product.product.split("_")[0]],
            "arrival": arrivals,
            "provenance": product.provenance.to_dict(),
        }
        explanation = self.explain.generate(
            payload,
            language=query.get("language", "en"),
            audience=query.get("audience", "forecaster"),
        )
        return self._json_response(200, explanation.to_dict())

    def openapi(self) -> dict[str, Any]:
        return {
            "openapi": "3.1.0",
            "info": {"title": "Metron Product API", "version": "1.0.0"},
            "paths": {
                "/v1/status": {"get": {"security": [{"bearerAuth": []}]}},
                "/v1/products": {"get": {"security": [{"bearerAuth": []}]}},
                "/v1/products/{product}": {"get": {"security": [{"bearerAuth": []}]}},
                "/v1/replay": {"post": {"security": [{"bearerAuth": []}], "x-role": "forecaster"}},
                "/v1/replay/{id}": {
                    "get": {"security": [{"bearerAuth": []}]},
                    "delete": {"x-role": "forecaster"},
                },
                "/v1/review/{issue}/draft-cap": {"post": {"x-role": "forecaster"}},
                "/v1/review/{alert_id}/approve": {"post": {"x-role": "forecaster"}},
                "/v1/explain/{issue}": {"get": {"security": [{"bearerAuth": []}]}},
                "/v1/targets": {
                    "get": {"security": [{"bearerAuth": []}]},
                    "post": {"x-role": "forecaster"},
                },
                "/v1/targets/{target_id}": {
                    "put": {"x-role": "forecaster"},
                    "delete": {"x-role": "forecaster"},
                },
                "/v1/ws": {
                    "get": {
                        "description": "WebSocket products.issued/status.changed/replay.tick events"
                    }
                },
            },
            "components": {
                "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}},
                "schemas": {
                    "Problem": {"type": "object", "required": ["type", "title", "status", "detail"]}
                },
            },
        }

    async def __call__(self, scope: Mapping[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            try:
                body = bytearray()
                while True:
                    message = await receive()
                    chunk = message.get("body", b"")
                    if len(body) + len(chunk) > MAX_REQUEST_BODY_BYTES:
                        raise Problem(
                            413,
                            "Payload Too Large",
                            f"request body exceeds {MAX_REQUEST_BODY_BYTES} bytes",
                        )
                    body.extend(chunk)
                    if not message.get("more_body", False):
                        break
                headers = {key.decode(): value.decode() for key, value in scope.get("headers", [])}
                url = scope.get("path", "/")
                query_string = scope.get("query_string", b"")
                if query_string:
                    url += "?" + query_string.decode()
                response = self.handle(scope["method"], url, headers, bytes(body))
            except Problem as exc:
                response = Response(
                    exc.status,
                    exc.body(),
                    {"content-type": "application/problem+json"},
                )
            content_type = response.headers.get("content-type", "")
            if isinstance(response.body, bytes):
                body_bytes = response.body
            elif isinstance(response.body, str) and (
                content_type.startswith("text/") or content_type == "application/cap+xml"
            ):
                body_bytes = response.body.encode()
            else:
                body_bytes = _json(response.body)
            headers_out = [
                (key.lower().encode(), value.encode()) for key, value in response.headers.items()
            ]
            headers_out.append((b"content-length", str(len(body_bytes)).encode()))
            await send(
                {"type": "http.response.start", "status": response.status, "headers": headers_out}
            )
            await send({"type": "http.response.body", "body": body_bytes})
            return
        if scope["type"] == "websocket":
            await self._websocket(scope, receive, send)
            return
        raise RuntimeError("unsupported ASGI scope")

    async def _websocket(self, scope: Mapping[str, Any], receive: Any, send: Any) -> None:
        headers = {key.decode(): value.decode() for key, value in scope.get("headers", [])}
        try:
            self.auth.require(headers, "viewer")
        except Problem:
            await send({"type": "websocket.close", "code": 4401})
            return
        await send({"type": "websocket.accept"})
        queue = self.hub.subscribe()
        receive_task = asyncio.create_task(receive())
        event_task = asyncio.create_task(queue.get())
        try:
            while True:
                done, _ = await asyncio.wait(
                    {receive_task, event_task}, return_when=asyncio.FIRST_COMPLETED
                )
                if receive_task in done:
                    message = receive_task.result()
                    if message.get("type") == "websocket.disconnect":
                        return
                    if message.get("type") == "websocket.receive" and message.get("text") == "ping":
                        await send({"type": "websocket.send", "text": json.dumps({"type": "pong"})})
                    receive_task = asyncio.create_task(receive())
                if event_task in done:
                    event = event_task.result()
                    await send(
                        {"type": "websocket.send", "text": json.dumps(event, ensure_ascii=False)}
                    )
                    event_task = asyncio.create_task(queue.get())
        finally:
            receive_task.cancel()
            event_task.cancel()
            self.hub.unsubscribe(queue)
