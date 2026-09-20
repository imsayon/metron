"""Small, dependency-light contracts for source ingestion.

The ingestion layer deliberately keeps source payloads opaque. Parsing a payload
into grids belongs to QC/grids; T1 records what arrived and why it was accepted.
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

UTC = timezone.utc


def utc_now() -> datetime:
    """Return an aware UTC timestamp suitable for an arrival clock."""

    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    """Normalize an aware timestamp to UTC without silently guessing a zone."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC)


def timestamp_text(value: datetime) -> str:
    """Serialize timestamps in the canonical manifest form."""

    return ensure_utc(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: Any, *, assume_utc: bool = True) -> datetime:
    """Parse the small set of timestamp forms used by public source payloads."""

    if isinstance(value, datetime):
        return ensure_utc(value)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, UTC)
    if not isinstance(value, str):
        raise ValueError(f"unsupported timestamp value: {value!r}")

    text = value.strip()
    if not text:
        raise ValueError("empty timestamp")
    upper = text.upper()
    if upper.endswith(" IST"):
        text = f"{text[:-4].strip()}+05:30"
    elif upper.endswith(" UTC"):
        text = text[:-4].strip() + "Z"
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if text.endswith("+0000") or text.endswith("-0000"):
        text = text[:-5] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = None
        for fmt in (
            "%d%b%Y %H%M",
            "%d%b%Y%H%M",
            "%Y%m%d%H%M",
            "%Y%m%d_%H%M",
            "%Y-%m-%d %H:%M",
            "%d/%m/%Y %H:%M",
            "%d-%m-%Y %H:%M",
        ):
            try:
                parsed = datetime.strptime(text.upper(), fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            raise ValueError(f"unrecognized timestamp: {value!r}") from None
    if parsed.tzinfo is None:
        if not assume_utc:
            raise ValueError(f"timestamp has no timezone: {value!r}")
        parsed = parsed.replace(tzinfo=UTC)
    return ensure_utc(parsed)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def manifest_id(source: str, station_or_sat: str, obs_time: datetime, payload_sha256: str) -> str:
    """Build the stable idempotency key specified by the data contract."""

    key = "|".join((source, station_or_sat, timestamp_text(obs_time), payload_sha256))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourceSpec:
    name: str
    access_class: str
    cadence_s: int
    expected_latency_s: int
    endpoint: str
    auth: str
    parser: str
    obs_time_rule: str
    retention_days: int | None
    attribution: str = ""
    terms_url: str = ""
    status: str = "not-started"
    settings: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "SourceSpec":
        data = dict(values)
        data["access_class"] = data.pop("class", data.get("access_class", ""))
        settings = {
            key: value
            for key, value in data.items()
            if key
            not in {
                "name",
                "access_class",
                "cadence_s",
                "expected_latency_s",
                "endpoint",
                "auth",
                "parser",
                "obs_time_rule",
                "retention_days",
                "attribution",
                "terms_url",
                "status",
            }
        }
        data["settings"] = settings
        return cls(
            name=str(data["name"]),
            access_class=str(data["access_class"]),
            cadence_s=int(data["cadence_s"]),
            expected_latency_s=int(data["expected_latency_s"]),
            endpoint=str(data["endpoint"]),
            auth=str(data.get("auth", "none")),
            parser=str(data["parser"]),
            obs_time_rule=str(data["obs_time_rule"]),
            retention_days=(
                None if data.get("retention_days") is None else int(data["retention_days"])
            ),
            attribution=str(data.get("attribution", "")),
            terms_url=str(data.get("terms_url", "")),
            status=str(data.get("status", "not-started")),
            settings=settings,
        )


@dataclass
class Observation:
    source: str
    station_or_sat: str
    payload: bytes
    obs_time: datetime
    arrival_time: datetime = field(default_factory=utc_now)
    issue_time: datetime | None = None
    valid_time: datetime | None = None
    content_type: str = "application/octet-stream"
    path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.obs_time = ensure_utc(self.obs_time)
        self.arrival_time = ensure_utc(self.arrival_time)
        self.issue_time = ensure_utc(self.issue_time or self.obs_time)
        self.valid_time = ensure_utc(self.valid_time or self.obs_time)
        if not isinstance(self.payload, bytes):
            self.payload = bytes(self.payload)

    @property
    def payload_sha256(self) -> str:
        return sha256_bytes(self.payload)

    @property
    def idempotency_key(self) -> str:
        return manifest_id(self.source, self.station_or_sat, self.obs_time, self.payload_sha256)

    def validate(self) -> None:
        if not self.source.strip():
            raise ValueError("source is required")
        if not self.station_or_sat.strip():
            raise ValueError("station_or_sat is required")
        if not self.payload:
            raise ValueError("empty payload")
        if self.issue_time > self.valid_time:
            raise ValueError("issue_time must not be after valid_time")
        if self.arrival_time < self.issue_time and not self.metadata.get("forecast", False):
            raise ValueError("arrival_time precedes issue_time")


@dataclass(frozen=True)
class ManifestRecord:
    idempotency_key: str
    source: str
    station_or_sat: str
    obs_time: datetime
    arrival_time: datetime
    issue_time: datetime
    valid_time: datetime
    payload_sha256: str
    payload_size: int
    path: str | None
    content_type: str
    status: str = "accepted"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_observation(
        cls,
        observation: Observation,
        *,
        path: str | None = None,
        status: str = "accepted",
    ) -> "ManifestRecord":
        observation.validate()
        return cls(
            idempotency_key=observation.idempotency_key,
            source=observation.source,
            station_or_sat=observation.station_or_sat,
            obs_time=observation.obs_time,
            arrival_time=observation.arrival_time,
            issue_time=observation.issue_time or observation.obs_time,
            valid_time=observation.valid_time or observation.obs_time,
            payload_sha256=observation.payload_sha256,
            payload_size=len(observation.payload),
            path=path or observation.path,
            content_type=observation.content_type,
            status=status,
            metadata=dict(observation.metadata),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "idempotency_key": self.idempotency_key,
            "source": self.source,
            "station_or_sat": self.station_or_sat,
            "obs_time": timestamp_text(self.obs_time),
            "arrival_time": timestamp_text(self.arrival_time),
            "issue_time": timestamp_text(self.issue_time),
            "valid_time": timestamp_text(self.valid_time),
            "payload_sha256": self.payload_sha256,
            "payload_size": self.payload_size,
            "path": self.path,
            "content_type": self.content_type,
            "status": self.status,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class HttpResponse:
    url: str
    status: int
    headers: Mapping[str, str]
    body: bytes
    received_at: datetime

    @property
    def content_type(self) -> str:
        value = next(
            (item for key, item in self.headers.items() if key.lower() == "content-type"),
            "",
        )
        return value.split(";", 1)[0].strip().lower()


class HttpClient(Protocol):
    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout_s: float = 30.0,
    ) -> HttpResponse: ...


class IngestError(Exception):
    """Base error for transport and validation failures."""


class TransportError(IngestError):
    retryable = True


class HttpStatusError(TransportError):
    def __init__(self, status: int, url: str, message: str = "") -> None:
        self.status = status
        self.url = url
        self.retryable = status == 408 or status == 429 or status >= 500
        super().__init__(message or f"HTTP {status} for {url}")


class QuarantineError(IngestError):
    """A source response was received but must not enter the manifest."""

    def __init__(
        self,
        reason: str,
        *,
        url: str | None = None,
        payload: bytes = b"",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.reason = reason
        self.url = url
        self.payload = payload
        self.details = dict(details or {})
        super().__init__(reason)


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    backoff_s: float = 0.5
    max_backoff_s: float = 30.0
    timeout_s: float = 30.0

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError("attempts must be positive")


class UrllibHttpClient:
    """Stdlib HTTP client; no source-specific dependency or credential store."""

    def __init__(
        self, *, user_agent: str = "Metron-ingest/0.1", max_bytes: int = 64 * 1024 * 1024
    ) -> None:
        self.user_agent = user_agent
        self.max_bytes = max_bytes

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout_s: float = 30.0,
    ) -> HttpResponse:
        request_headers = {"User-Agent": self.user_agent, **dict(headers or {})}
        request = Request(url, headers=request_headers, method="GET")
        try:
            with urlopen(request, timeout=timeout_s) as response:
                body = response.read(self.max_bytes + 1)
                if len(body) > self.max_bytes:
                    raise TransportError(f"response exceeds {self.max_bytes} bytes: {url}")
                return HttpResponse(
                    url=url,
                    status=int(response.status),
                    headers={str(k): str(v) for k, v in response.headers.items()},
                    body=body,
                    received_at=utc_now(),
                )
        except HTTPError as exc:
            raise HttpStatusError(exc.code, url) from exc
        except URLError as exc:
            raise TransportError(f"request failed for {url}: {exc.reason}") from exc
        except TimeoutError as exc:
            raise TransportError(f"request timed out for {url}") from exc


class RetryingHttpClient:
    def __init__(
        self,
        client: HttpClient,
        policy: RetryPolicy | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client
        self.policy = policy or RetryPolicy()
        self.sleep = sleep

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
    ) -> HttpResponse:
        last_error: Exception | None = None
        for attempt in range(self.policy.attempts):
            try:
                return self.client.get(
                    url,
                    headers=headers,
                    timeout_s=timeout_s or self.policy.timeout_s,
                )
            except (TransportError, OSError) as exc:
                last_error = exc
                if isinstance(exc, HttpStatusError) and not exc.retryable:
                    raise
                if attempt + 1 == self.policy.attempts:
                    raise
                delay = min(self.policy.max_backoff_s, self.policy.backoff_s * (2**attempt))
                self.sleep(delay)
        raise TransportError(f"request failed for {url}: {last_error}")


class SourceAdapter(Protocol):
    spec: SourceSpec

    def poll(self, now: datetime | None = None) -> Iterable[Observation]:
        """Fetch and validate the source's current payload(s)."""


def load_source_specs(directory: str | os.PathLike[str]) -> dict[str, SourceSpec]:
    """Load committed YAML source manifests without making network calls."""

    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - only minimal installations
        raise RuntimeError("PyYAML is required to load source manifests") from exc

    result: dict[str, SourceSpec] = {}
    for path in sorted(Path(directory).glob("*.yaml")):
        with path.open("r", encoding="utf-8") as handle:
            values = yaml.safe_load(handle) or {}
        spec = SourceSpec.from_mapping(values)
        if spec.name in result:
            raise ValueError(f"duplicate source manifest: {spec.name}")
        result[spec.name] = spec
    return result


def encode_query(params: Mapping[str, Any]) -> str:
    """Stable query encoding used by the GFS adapter and test fakes."""

    return urlencode([(key, str(value)) for key, value in sorted(params.items())])
