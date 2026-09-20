"""CAP 1.2 draft composition with an explicit approval boundary."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from xml.etree import ElementTree

CAP_NS = "urn:oasis:names:tc:emergency:cap:1.2"
ElementTree.register_namespace("", CAP_NS)


def _utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("CAP timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _iso(value: datetime | str) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _add(parent: ElementTree.Element, name: str, value: Any) -> ElementTree.Element:
    child = ElementTree.SubElement(parent, f"{{{CAP_NS}}}{name}")
    child.text = str(value)
    return child


class CAPComposer:
    """Compose CAP XML; this class has no delivery method by design."""

    sender = "metron@example.invalid"
    sender_name = "Metron (experimental) — not an official IMD warning"

    def compose(
        self,
        *,
        alert_id: str,
        domain: str,
        issue_time: datetime | str,
        hazards: Iterable[str],
        targets: Iterable[dict[str, Any]],
        probability: float = 0.0,
        t10_min: int | None = None,
        t90_min: int | None = None,
        description: str | None = None,
        status: str = "Test",
        approved_by: str | None = None,
    ) -> str:
        if not alert_id.strip() or not domain.strip():
            raise ValueError("alert_id and domain are required")
        if status not in {"Test", "Actual"}:
            raise ValueError("CAP status must be Test or Actual")
        if not 0 <= probability <= 1:
            raise ValueError("probability must be between 0 and 1")
        hazard_names = tuple(item.strip() for item in hazards if item.strip())
        if not hazard_names:
            raise ValueError("at least one hazard is required")
        target_list = tuple(targets)
        target_text = ", ".join(
            str(item.get("name", item.get("target_id", "target"))) for item in target_list
        )
        event = "/".join(hazard_names)
        issue = _utc(issue_time)
        onset = issue + (timedelta(minutes=t10_min) if t10_min is not None else timedelta(0))
        expires = issue + (
            timedelta(minutes=t90_min) if t90_min is not None else timedelta(hours=6)
        )
        root = ElementTree.Element(f"{{{CAP_NS}}}alert")
        _add(root, "identifier", alert_id)
        _add(root, "sender", self.sender)
        _add(root, "sent", _iso(datetime.now(timezone.utc)))
        _add(root, "status", status)
        _add(root, "msgType", "Alert")
        _add(root, "scope", "Public")
        info = ElementTree.SubElement(root, f"{{{CAP_NS}}}info")
        _add(info, "language", "en-US")
        _add(info, "category", "Met")
        _add(info, "event", f"{event} nowcast guidance (experimental)")
        urgency = "Immediate" if t10_min is not None and t10_min <= 30 else "Expected"
        _add(info, "urgency", urgency)
        _add(
            info,
            "severity",
            "Severe" if probability >= 0.7 else "Moderate" if probability >= 0.4 else "Minor",
        )
        _add(
            info,
            "certainty",
            "Likely" if probability >= 0.6 else "Possible" if probability >= 0.3 else "Unlikely",
        )
        _add(info, "onset", _iso(onset))
        _add(info, "expires", _iso(min(expires, issue + timedelta(hours=6))))
        _add(info, "senderName", self.sender_name)
        headline = f"{event} likely near {target_text or 'the selected area'} (P={probability:g})"
        _add(info, "headline", headline)
        _add(
            info,
            "description",
            description or f"{headline}. {self.sender_name}",
        )
        _add(
            info, "instruction", "Treat as experimental guidance and seek forecaster confirmation."
        )
        for key, value in {
            "domain": domain,
            "probability": probability,
            "approved_by": approved_by or "",
            "external_delivery": "disabled",
        }.items():
            parameter = ElementTree.SubElement(info, f"{{{CAP_NS}}}parameter")
            _add(parameter, "valueName", key)
            _add(parameter, "value", value)
        area = ElementTree.SubElement(info, f"{{{CAP_NS}}}area")
        _add(area, "areaDesc", target_text or domain)
        for target in target_list:
            if "latitude" in target and "longitude" in target:
                _add(area, "point", f"{target['latitude']},{target['longitude']}")
        return ElementTree.tostring(root, encoding="unicode")
