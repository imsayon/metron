"""Typed product contracts and storage boundaries for Metron."""

from .contracts import (
    Abstention,
    ContractError,
    InputProvenance,
    ProductSummary,
    Provenance,
    Target,
    fixture_product,
    validate_product_summary,
    validate_provenance,
)
from .writers import (
    COGWriter,
    EventPublisher,
    MemoryCOGWriter,
    MemoryPostGISWriter,
    PostGISWriter,
    ProductWriter,
)

__all__ = [
    "Abstention",
    "COGWriter",
    "ContractError",
    "EventPublisher",
    "InputProvenance",
    "MemoryCOGWriter",
    "MemoryPostGISWriter",
    "PostGISWriter",
    "ProductSummary",
    "ProductWriter",
    "Provenance",
    "Target",
    "fixture_product",
    "validate_product_summary",
    "validate_provenance",
]
