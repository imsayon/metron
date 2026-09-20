"""Versioned label catalogue contracts for Metron."""

from .catalogue import (
    LabelCatalogue,
    LabelEvidence,
    LabelEvent,
    LabelValidationError,
)
from .definitions import DEFINITION_VERSION, HAZARD_DEFINITIONS

__all__ = [
    "DEFINITION_VERSION",
    "HAZARD_DEFINITIONS",
    "LabelCatalogue",
    "LabelEvidence",
    "LabelEvent",
    "LabelValidationError",
]
