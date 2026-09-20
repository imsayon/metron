"""Storage interfaces for validated products.

Real COG and PostGIS adapters can implement the protocols without changing the
product contract or API.  The in-memory implementations are fixture-safe.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Protocol, runtime_checkable

from .contracts import ProductSummary, validate_product_summary


@runtime_checkable
class COGWriter(Protocol):
    def write(self, summary: ProductSummary, payload: bytes | None = None) -> str:
        """Persist a validated raster and return its immutable object URL."""


@runtime_checkable
class PostGISWriter(Protocol):
    def upsert_product(self, summary: ProductSummary) -> None:
        """Persist the product index and spatial metadata."""


@runtime_checkable
class EventPublisher(Protocol):
    def publish(self, event: Mapping[str, Any]) -> None:
        """Publish a product-issued event to the API/WebSocket boundary."""


class MemoryCOGWriter:
    """Fixture writer; it does not claim to create a production COG."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def write(self, summary: ProductSummary, payload: bytes | None = None) -> str:
        summary = validate_product_summary(summary)
        key = summary.cog_url
        self.objects[key] = payload or b"fixture-cog-payload"
        return key


class MemoryPostGISWriter:
    """Fixture index with the same upsert boundary as a PostGIS adapter."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str, str, int], dict[str, Any]] = {}

    def upsert_product(self, summary: ProductSummary) -> None:
        summary = validate_product_summary(summary)
        key = (
            summary.provenance.domain,
            summary.provenance.issue_time.isoformat(),
            summary.product,
            summary.lead_min,
        )
        self.rows[key] = deepcopy(summary.to_dict())


class ProductWriter:
    """Validate once, write both stores, then emit one products.issued event."""

    def __init__(
        self,
        cog: COGWriter,
        postgis: PostGISWriter,
        events: EventPublisher | None = None,
    ) -> None:
        self.cog = cog
        self.postgis = postgis
        self.events = events

    def write(self, product: ProductSummary, payload: bytes | None = None) -> ProductSummary:
        product = validate_product_summary(product)
        self.cog.write(product, payload)
        self.postgis.upsert_product(product)
        if self.events is not None:
            self.events.publish(
                {
                    "type": "products.issued",
                    "domain": product.provenance.domain,
                    "issue_time": product.provenance.issue_time.isoformat().replace(
                        "+00:00", "Z"
                    ),
                    "product": product.product,
                    "lead_min": product.lead_min,
                    "rung": product.provenance.rung,
                    "abstentions": [
                        item.to_dict() for item in product.provenance.abstentions
                    ],
                    "mode": product.provenance.mode,
                    "replay_id": product.provenance.replay_id,
                }
            )
        return product
