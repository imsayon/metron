"""Evidence-preserving adapters for the four T1 public source families."""

from __future__ import annotations

import base64
import io
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import urlsplit

from .contracts import (
    HttpClient,
    HttpResponse,
    HttpStatusError,
    Observation,
    QuarantineError,
    RetryingHttpClient,
    RetryPolicy,
    SourceSpec,
    TransportError,
    UrllibHttpClient,
    encode_query,
    parse_timestamp,
    utc_now,
)

UTC = timezone.utc


def _text(payload: bytes) -> str:
    return payload.decode("latin-1", errors="ignore")


_ISO_RE = re.compile(
    r"(?P<date>20\d{2}[-/]\d{2}[-/]\d{2})[T _-](?P<time>\d{2}:?\d{2}(?::?\d{2})?(?:\.\d+)?)"
    r"(?P<zone>Z|[+-]\d{2}:?\d{2})?",
    re.IGNORECASE,
)
_COMPACT_RE = re.compile(
    r"(?P<date>20\d{6})[T _-]?(?P<time>\d{4,6})(?P<zone>Z|[+-]\d{4})?",
    re.IGNORECASE,
)
_MONTH_RE = re.compile(
    r"(?P<day>\d{2})(?P<month>[A-Z]{3})(?P<year>20\d{2})[ T_-]?(?P<hour>\d{2})[:_-]?(?P<minute>\d{2})(?::?(?P<second>\d{2}))?",
    re.IGNORECASE,
)


def extract_timestamp(payload: bytes, url: str = "", *, ocr: Callable[[bytes], str] | None = None) -> tuple[datetime, str]:
    """Extract a source timestamp from a header, filename, or injected OCR result."""

    candidates = (_text(payload), url)
    for source, candidate in (("header", candidates[0]), ("url", candidates[1])):
        for match in _ISO_RE.finditer(candidate):
            try:
                value = match.group("date") + "T" + match.group("time") + (match.group("zone") or "Z")
                return parse_timestamp(value), source
            except ValueError:
                continue
        for match in _COMPACT_RE.finditer(candidate):
            try:
                date = match.group("date")
                clock = match.group("time").ljust(6, "0")
                value = f"{date[:4]}-{date[4:6]}-{date[6:]}T{clock[:2]}:{clock[2:4]}:{clock[4:]}"
                zone = match.group("zone")
                if zone:
                    value += "+00:00" if zone.upper() == "Z" else zone[:3] + ":" + zone[3:]
                return parse_timestamp(value), source
            except ValueError:
                continue
        for match in _MONTH_RE.finditer(candidate.upper()):
            try:
                date = f"{match.group('day')}{match.group('month')}{match.group('year')}"
                clock = f"{match.group('hour')}{match.group('minute')}"
                if match.group("second"):
                    clock += f":{match.group('second')}"
                value = f"{date} {clock}"
                return parse_timestamp(value), source
            except ValueError:
                continue

    if ocr is not None:
        ocr_text = ocr(payload)
        timestamp, _ = extract_timestamp(ocr_text.encode("utf-8"), "")
        return timestamp, "ocr"
    raise ValueError("no source timestamp found")


def _image_payload(response: HttpResponse) -> bool:
    return response.content_type.startswith("image/") or response.body.startswith(
        (b"GIF87a", b"GIF89a", b"\x89PNG", b"\xff\xd8\xff")
    )


def _require_payload(response: HttpResponse, *, url: str, kind: str) -> None:
    if response.status < 200 or response.status >= 300:
        raise HttpStatusError(response.status, url)
    if not response.body:
        raise QuarantineError("empty_payload", url=url, details={"kind": kind})


def _check_time(
    timestamp: datetime,
    arrival: datetime,
    *,
    max_age_s: int | None = None,
    future_tolerance_s: int = 300,
) -> None:
    if timestamp > arrival + timedelta(seconds=future_tolerance_s):
        raise QuarantineError("future_observation", details={"obs_time": timestamp.isoformat()})
    if max_age_s is not None and arrival - timestamp > timedelta(seconds=max_age_s):
        raise QuarantineError("stale_observation", details={"obs_time": timestamp.isoformat()})


class HttpAdapter:
    def __init__(
        self,
        spec: SourceSpec,
        *,
        client: HttpClient | None = None,
        retry_policy: RetryPolicy | None = None,
        sleep: Callable[[float], None] | None = None,
        clock: Callable[[], datetime] = utc_now,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.spec = spec
        base_client = client or UrllibHttpClient()
        if isinstance(base_client, RetryingHttpClient):
            self.client = base_client
        else:
            policy = retry_policy or RetryPolicy()
            self.client = RetryingHttpClient(
                base_client,
                policy,
                sleep=sleep or __import__("time").sleep,
            )
        self.clock = clock
        self.headers = dict(headers or {})

    def _get(self, url: str, *, headers: Mapping[str, str] | None = None) -> HttpResponse:
        return self.client.get(url, headers={**self.headers, **dict(headers or {})})

    def _max_age(self, value: int | None = None) -> int | None:
        if value is not None:
            return value
        configured = self.spec.settings.get("max_obs_age_s")
        return None if configured is None else int(configured)


class InsatBrowseAdapter(HttpAdapter):
    """Fetch public browse images and require an evidence-bearing timestamp.

    Browse images are intentionally marked ``calibrated=0``. A successful HTTP
    response alone is not treated as a usable observation: an empty or untimed
    response is quarantined.
    """

    def __init__(
        self,
        spec: SourceSpec,
        urls: Sequence[str] | None = None,
        *,
        ocr: Callable[[bytes], str] | None = None,
        satellite: str | None = None,
        client: HttpClient | None = None,
        retry_policy: RetryPolicy | None = None,
        sleep: Callable[[float], None] | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        super().__init__(spec, client=client, retry_policy=retry_policy, sleep=sleep, clock=clock)
        configured = spec.settings.get("urls", spec.settings.get("products", []))
        self.urls = list(urls or configured)
        self.ocr = ocr
        self.satellite = satellite
        if not self.urls:
            raise ValueError("insat_browse requires at least one concrete URL")

    def poll(self, now: datetime | None = None) -> Iterable[Observation]:
        del now
        for url in self.urls:
            response = self._get(url)
            _require_payload(response, url=url, kind="insat_browse")
            if not _image_payload(response):
                raise QuarantineError("not_an_image", url=url, payload=response.body)
            arrival = response.received_at or self.clock()
            try:
                obs_time, timestamp_source = extract_timestamp(response.body, url, ocr=self.ocr)
            except ValueError as exc:
                raise QuarantineError(
                    "missing_source_timestamp",
                    url=url,
                    payload=response.body,
                    details={"error": str(exc)},
                ) from exc
            _check_time(obs_time, arrival, max_age_s=self._max_age())
            satellite = self.satellite or self._satellite_from_url(url)
            product = self._product_from_url(url)
            yield Observation(
                source=self.spec.name,
                station_or_sat=satellite,
                payload=response.body,
                obs_time=obs_time,
                arrival_time=arrival,
                issue_time=obs_time,
                valid_time=obs_time,
                content_type=response.content_type or "image/jpeg",
                metadata={
                    "calibrated": False,
                    "obs_time_source": timestamp_source,
                    "product": product,
                    "source_class": self.spec.access_class,
                },
            )

    @staticmethod
    def _satellite_from_url(url: str) -> str:
        upper = url.upper()
        if "3RIMG" in upper:
            return "INSAT-3DR"
        if "3SIMG" in upper:
            return "INSAT-3DS"
        if "3DIMG" in upper:
            return "INSAT-3D"
        return "INSAT-UNKNOWN"

    @staticmethod
    def _product_from_url(url: str) -> str:
        match = re.search(r"(?:3[DRS]IMG|PROD)[^A-Z0-9]*(?:\d{8}[^A-Z0-9]*)?([A-Z0-9]+)", url.upper())
        return match.group(1) if match else "UNKNOWN"


@dataclass(frozen=True)
class RadarDecodeSummary:
    width: int
    height: int
    known_pixels: int
    unknown_pixels: int
    histogram: Mapping[float, int]

    @property
    def unknown_fraction(self) -> float:
        total = self.known_pixels + self.unknown_pixels
        return 0.0 if total == 0 else self.unknown_pixels / total


def decode_radar_palette(payload: bytes, value_by_palette_index: Mapping[int, float]) -> RadarDecodeSummary:
    """Decode a configured radar image palette without guessing station colors."""

    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise RuntimeError("Pillow is required to decode radar images") from exc
    try:
        with Image.open(io.BytesIO(payload)) as image:
            indexed = image.convert("P")
            if hasattr(indexed, "get_flattened_data"):
                pixels = list(indexed.get_flattened_data())
            else:  # pragma: no cover - compatibility with older Pillow
                pixels = list(indexed.getdata())
            histogram: Counter[float] = Counter()
            unknown = 0
            for pixel in pixels:
                value = value_by_palette_index.get(int(pixel))
                if value is None:
                    unknown += 1
                else:
                    histogram[float(value)] += 1
            return RadarDecodeSummary(
                width=indexed.width,
                height=indexed.height,
                known_pixels=len(pixels) - unknown,
                unknown_pixels=unknown,
                histogram=dict(histogram),
            )
    except Exception as exc:
        raise QuarantineError("radar_image_decode_failed", payload=payload, details={"error": str(exc)}) from exc


class ImdRadarProductAdapter(HttpAdapter):
    """Fetch rendered IMD radar products; raw volumes are a separate source."""

    PRODUCTS = ("caz", "ppz", "ppv", "sri", "pac", "vp2")

    def __init__(
        self,
        spec: SourceSpec,
        stations: Sequence[str] | None = None,
        products: Sequence[str] | None = None,
        *,
        urls: Sequence[tuple[str, str, str]] | None = None,
        palette: Mapping[int, float] | None = None,
        client: HttpClient | None = None,
        retry_policy: RetryPolicy | None = None,
        sleep: Callable[[float], None] | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        super().__init__(spec, client=client, retry_policy=retry_policy, sleep=sleep, clock=clock)
        self.stations = [str(item) for item in (stations or spec.settings.get("stations", []))]
        self.products = [str(item).lower() for item in (products or spec.settings.get("products", self.PRODUCTS))]
        self.palette = dict(palette or {})
        invalid = set(self.products) - set(self.PRODUCTS)
        if invalid:
            raise ValueError(f"unsupported IMD radar products: {sorted(invalid)}")
        self.urls = list(urls or [])
        if not self.urls and not self.stations:
            raise ValueError("imd_radar_products requires stations or concrete urls")

    def poll(self, now: datetime | None = None) -> Iterable[Observation]:
        del now
        requests = self.urls or [
            (station, product, self.spec.endpoint.format(station=station, product=product))
            for station in self.stations
            for product in self.products
        ]
        for station, product, url in requests:
            response = self._get(url)
            _require_payload(response, url=url, kind="imd_radar_products")
            if not _image_payload(response):
                raise QuarantineError("not_an_image", url=url, payload=response.body)
            arrival = response.received_at or self.clock()
            metadata: dict[str, Any] = {
                "product": product,
                "channel": self._channel(product),
                "has_velocity": product == "ppv",
                "source_class": self.spec.access_class,
            }
            if self.palette:
                summary = decode_radar_palette(response.body, self.palette)
                metadata["decode_summary"] = {
                    "width": summary.width,
                    "height": summary.height,
                    "known_pixels": summary.known_pixels,
                    "unknown_pixels": summary.unknown_pixels,
                    "unknown_fraction": summary.unknown_fraction,
                    "histogram": dict(summary.histogram),
                }
            try:
                obs_time, timestamp_source = extract_timestamp(response.body, url)
                metadata["obs_time_source"] = timestamp_source
                metadata["obs_time_estimated"] = False
            except ValueError:
                obs_time = arrival - timedelta(seconds=300)
                metadata["obs_time_source"] = "arrival_minus_5m"
                metadata["obs_time_estimated"] = True
            _check_time(obs_time, arrival, max_age_s=self._max_age())
            yield Observation(
                source=self.spec.name,
                station_or_sat=station,
                payload=response.body,
                obs_time=obs_time,
                arrival_time=arrival,
                issue_time=obs_time,
                valid_time=obs_time,
                content_type=response.content_type or "image/gif",
                metadata=metadata,
            )

    @staticmethod
    def _channel(product: str) -> str:
        return {
            "caz": "zmax",
            "ppz": "z_cappi1_proxy",
            "ppv": "vr_lowest",
            "sri": "sri",
            "pac": "pac",
            "vp2": "vp2",
        }[product]


class GfsAdapter(HttpAdapter):
    """Fetch latency-aware GFS GRIB2 subsets from NOAA NOMADS."""

    def __init__(
        self,
        spec: SourceSpec,
        *,
        cycle: datetime | None = None,
        steps: Sequence[int] | None = None,
        client: HttpClient | None = None,
        retry_policy: RetryPolicy | None = None,
        sleep: Callable[[float], None] | None = None,
        clock: Callable[[], datetime] = utc_now,
        query: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(spec, client=client, retry_policy=retry_policy, sleep=sleep, clock=clock)
        self.cycle = None if cycle is None else cycle.astimezone(UTC)
        configured_steps = steps or spec.settings.get("forecast_steps", [0])
        self.steps = [int(step) for step in configured_steps]
        if any(step < 0 or step > 384 for step in self.steps):
            raise ValueError("GFS forecast steps must be between 0 and 384 hours")
        self.query = dict(query or spec.settings.get("query", {}))

    def poll(self, now: datetime | None = None) -> Iterable[Observation]:
        now = (now or self.clock()).astimezone(UTC)
        cycle = self.cycle or self._latest_available_cycle(now)
        for step in self.steps:
            valid = cycle + timedelta(hours=step)
            url = self.build_url(cycle, step)
            response = self._get(url)
            _require_payload(response, url=url, kind="gfs")
            if not response.body.startswith(b"GRIB"):
                raise QuarantineError("not_grib2", url=url, payload=response.body)
            arrival = response.received_at or self.clock()
            yield Observation(
                source=self.spec.name,
                station_or_sat="gfs",
                payload=response.body,
                obs_time=valid,
                arrival_time=arrival,
                issue_time=cycle,
                valid_time=valid,
                content_type=response.content_type or "application/octet-stream",
                metadata={
                    "forecast": True,
                    "cycle_used": cycle.isoformat().replace("+00:00", "Z"),
                    "forecast_step_h": step,
                    "source_class": self.spec.access_class,
                },
            )

    def build_url(self, cycle: datetime, step: int) -> str:
        cycle = cycle.astimezone(UTC)
        filename = f"gfs.t{cycle:%H}z.pgrb2.0p25.f{step:03d}"
        directory = f"/gfs.{cycle:%Y%m%d}/{cycle:%H}/atmos"
        if "{" in self.spec.endpoint:
            return self.spec.endpoint.format(
                file=filename,
                directory=directory,
                date=cycle.strftime("%Y%m%d"),
                cycle=cycle.strftime("%H"),
                step=f"{step:03d}",
            )
        params: dict[str, Any] = {
            "dir": directory,
            "file": filename,
            "leftlon": "60",
            "rightlon": "100",
            "toplat": "40",
            "bottomlat": "0",
            "lev_surface": "on",
            "var_CAPE": "on",
            "var_CIN": "on",
            "var_PRATE": "on",
            "var_PWAT": "on",
            "var_UGRD": "on",
            "var_VGRD": "on",
            **self.query,
        }
        return f"{self.spec.endpoint}?{encode_query(params)}"

    def _latest_available_cycle(self, now: datetime) -> datetime:
        eligible = now - timedelta(seconds=self.spec.expected_latency_s)
        cycle_hour = (eligible.hour // 6) * 6
        cycle = eligible.replace(hour=cycle_hour, minute=0, second=0, microsecond=0)
        if cycle > eligible:
            cycle -= timedelta(hours=6)
        return cycle


def _normal_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


_ISSUE_KEYS = {
    "issuetime",
    "issuedat",
    "issuedon",
    "updatedat",
    "obstime",
    "observationtime",
    "observationdate",
    "timestamp",
    "datetime",
    "date",
}
_VALID_KEYS = {"validtime", "validfrom", "validuntil", "validto", "validity"}


def _timestamp_fields(value: Any, *, top_level: bool = False) -> tuple[datetime | None, datetime | None, list[datetime]]:
    issue: datetime | None = None
    valid: datetime | None = None
    all_times: list[datetime] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = _normal_key(str(key))
            if isinstance(item, (str, int, float, datetime)):
                try:
                    parsed = parse_timestamp(item)
                except (TypeError, ValueError):
                    parsed = None
                if parsed is not None:
                    all_times.append(parsed)
                    if normalized in _VALID_KEYS and valid is None:
                        valid = parsed
                    elif normalized in _ISSUE_KEYS and issue is None:
                        issue = parsed
            if isinstance(item, (Mapping, list, tuple)):
                nested_issue, nested_valid, nested_times = _timestamp_fields(item)
                issue = issue or nested_issue
                valid = valid or nested_valid
                all_times.extend(nested_times)
    elif isinstance(value, (list, tuple)):
        for item in value:
            nested_issue, nested_valid, nested_times = _timestamp_fields(item)
            issue = issue or nested_issue
            valid = valid or nested_valid
            all_times.extend(nested_times)
    return issue, valid, all_times


def parse_nowcast_categories(payload: Any) -> list[dict[str, Any]]:
    """Extract categorical nowcast rows without changing the source response."""

    categories: list[dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            category_key = next(
                (
                    key
                    for key in ("category", "warning", "colour", "color", "severity", "nowcast")
                    if key in value and value[key] is not None
                ),
                None,
            )
            if category_key is not None:
                row = {
                    "category": str(value[category_key]),
                    "district": value.get("district") or value.get("district_name"),
                    "station": value.get("station") or value.get("station_name"),
                    "valid_from": value.get("valid_from") or value.get("validFrom"),
                    "valid_to": value.get("valid_to") or value.get("validTo"),
                }
                categories.append(row)
            for item in value.values():
                visit(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)

    visit(payload)
    return categories


class ImdApiAdapter(HttpAdapter):
    """Archive an IMD JSON response verbatim and expose parsed categories."""

    def __init__(
        self,
        spec: SourceSpec,
        *,
        endpoint: str | None = None,
        kind: str = "json",
        scope: str = "india",
        api_key: str | None = None,
        client: HttpClient | None = None,
        retry_policy: RetryPolicy | None = None,
        sleep: Callable[[float], None] | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        headers = {"Accept": "application/json"}
        if api_key:
            headers["x-api-key"] = api_key
        super().__init__(spec, client=client, retry_policy=retry_policy, sleep=sleep, clock=clock, headers=headers)
        self.endpoint = endpoint or spec.endpoint
        self.kind = kind
        self.scope = scope

    def poll(self, now: datetime | None = None) -> Iterable[Observation]:
        del now
        response = self._get(self.endpoint)
        _require_payload(response, url=self.endpoint, kind="imd_api")
        try:
            payload = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise QuarantineError(
                "invalid_json",
                url=self.endpoint,
                payload=response.body,
                details={"error": str(exc)},
            ) from exc
        if not isinstance(payload, (Mapping, list)):
            raise QuarantineError("unexpected_json_shape", url=self.endpoint, payload=response.body)
        issue, valid, all_times = _timestamp_fields(payload, top_level=True)
        if issue is None and all_times:
            issue = all_times[0]
        if issue is None:
            raise QuarantineError("missing_source_timestamp", url=self.endpoint, payload=response.body)
        valid = valid or issue
        obs_time = issue
        metadata: dict[str, Any] = {
            "kind": self.kind,
            "scope": self.scope,
            "category_count": len(parse_nowcast_categories(payload)) if "nowcast" in self.kind else 0,
            "source_class": self.spec.access_class,
        }
        if all_times:
            metadata["payload_times"] = [item.isoformat().replace("+00:00", "Z") for item in all_times[:64]]
        arrival = response.received_at or self.clock()
        _check_time(obs_time, arrival, max_age_s=self._max_age())
        yield Observation(
            source=self.spec.name,
            station_or_sat=self.scope,
            payload=response.body,
            obs_time=obs_time,
            arrival_time=arrival,
            issue_time=issue,
            valid_time=valid,
            content_type=response.content_type or "application/json",
            metadata=metadata,
        )


# Explicit aliases keep source-family names discoverable to callers.
InsatBrowseSourceAdapter = InsatBrowseAdapter
ImdRadarSourceAdapter = ImdRadarProductAdapter
GFSAdapter = GfsAdapter
IMDAPIAdapter = ImdApiAdapter
