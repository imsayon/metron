"""Deterministic, guardrailed explanation output."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


KNOWN_HAZARDS = {"lightning", "thunderstorm", "hail", "downburst", "cloudburst", "rain"}
NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)?")


def _number(value: Any) -> str:
    try:
        decimal = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        return str(value)
    return format(decimal.normalize(), "f")


def _numbers(payload: Mapping[str, Any]) -> tuple[str, ...]:
    rows = payload.get("arrival", payload.get("arrivals", []))
    if rows is None:
        rows = []
    if isinstance(rows, Mapping):
        rows = [rows]
    result: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        for key in ("p_arrival", "t10_min", "t50_min", "t90_min"):
            if key in row and row[key] is not None:
                result.append(_number(row[key]))
    return tuple(dict.fromkeys(result))


def _text_numbers(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_number(value) for value in NUMBER_RE.findall(text)))


def _hazards(payload: Mapping[str, Any]) -> set[str]:
    raw = payload.get("hazards", payload.get("hazard", []))
    if isinstance(raw, str):
        raw = [raw]
    return {str(item).lower() for item in raw}


def check_explanation(text: str, payload: Mapping[str, Any], audience: str = "public") -> tuple[bool, tuple[str, ...]]:
    required = _numbers(payload)
    present = set(_text_numbers(text))
    missing = [f"number:{value}" for value in required if value not in present]
    watermark = str(payload.get("provenance", {}).get("watermark", "EXPERIMENTAL GUIDANCE — NOT AN OFFICIAL IMD WARNING"))
    if watermark not in text:
        missing.append("watermark")
    target = payload.get("target")
    if not target and payload.get("arrival"):
        first = payload["arrival"][0] if isinstance(payload["arrival"], list) else payload["arrival"]
        target = first.get("target", {}) if isinstance(first, Mapping) else {}
    target_name = target.get("name") if isinstance(target, Mapping) else None
    if target_name and str(target_name) not in text:
        missing.append("target")
    known_in_payload = _hazards(payload)
    for hazard in KNOWN_HAZARDS - known_in_payload:
        if re.search(rf"\b{re.escape(hazard)}\b", text, re.IGNORECASE):
            missing.append(f"unexpected-hazard:{hazard}")
    if audience == "public" and len(text) > 600:
        missing.append("public-length")
    return not missing, tuple(missing)


@dataclass(frozen=True)
class Explanation:
    text: str
    generated: bool
    numbers_checked: bool
    prompt_hash: str
    response_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "generated": self.generated,
            "numbers_checked": self.numbers_checked,
            "prompt_hash": self.prompt_hash,
            "response_hash": self.response_hash,
        }


class ExplanationService:
    def generate(
        self,
        payload: Mapping[str, Any],
        *,
        language: str = "en",
        audience: str = "forecaster",
        candidate: str | None = None,
    ) -> Explanation:
        if language not in {"en", "hi", "bn"}:
            raise ValueError("language must be en, hi, or bn")
        if audience not in {"forecaster", "ddma", "public"}:
            raise ValueError("audience must be forecaster, ddma, or public")
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        prompt_hash = hashlib.sha256(canonical.encode()).hexdigest()
        text = candidate or self._template(payload, language)
        valid, _ = check_explanation(text, payload, audience)
        if not valid:
            text = self._template(payload, language)
            valid, reasons = check_explanation(text, payload, audience)
            if not valid:
                raise ValueError(f"unable to satisfy explanation guardrail: {', '.join(reasons)}")
        return Explanation(
            text=text,
            generated=True,
            numbers_checked=True,
            prompt_hash=prompt_hash,
            response_hash=hashlib.sha256(text.encode()).hexdigest(),
        )

    def _template(self, payload: Mapping[str, Any], language: str) -> str:
        rows = payload.get("arrival", payload.get("arrivals", []))
        row = rows[0] if isinstance(rows, list) and rows else rows if isinstance(rows, Mapping) else {}
        target = payload.get("target") or row.get("target", {})
        target_name = target.get("name", target.get("target_id", "selected target")) if isinstance(target, Mapping) else "selected target"
        hazard_values = payload.get("hazards", [payload.get("product", "hazard")])
        hazard = ", ".join(str(item) for item in hazard_values) if not isinstance(hazard_values, str) else hazard_values
        watermark = payload.get("provenance", {}).get("watermark", "EXPERIMENTAL GUIDANCE — NOT AN OFFICIAL IMD WARNING")
        if not row:
            return f"{hazard} guidance near {target_name}. {watermark}"
        return (
            f"{hazard} guidance near {target_name}: P={_number(row['p_arrival'])}; "
            f"window T10={_number(row['t10_min'])}–T90={_number(row['t90_min'])} min "
            f"(T50={_number(row['t50_min'])}). {watermark}"
        )
