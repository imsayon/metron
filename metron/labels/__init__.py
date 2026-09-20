"""Versioned label catalogue contracts for Metron."""

from .catalogue import (
    LabelCatalogue,
    LabelEvent,
    LabelEvidence,
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
