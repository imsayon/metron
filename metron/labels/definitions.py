"""Label definitions mirrored from the private Metron data specification."""

from __future__ import annotations

from dataclasses import dataclass

DEFINITION_VERSION = "1"


@dataclass(frozen=True)
class HazardDefinition:
    hazard: str
    positive_definition: str
    truth_source: str
    proxy: bool = False


HAZARD_DEFINITIONS = {
    "lightning_30": HazardDefinition(
        "lightning_30",
        "At least one ILLN flash within 8 km in the next 30 minutes.",
        "ILLN",
    ),
    "lightning_60": HazardDefinition(
        "lightning_60",
        "At least one ILLN flash within 8 km in the next 60 minutes.",
        "ILLN",
    ),
    "ci_30": HazardDefinition(
        "ci_30",
        "First 35 dBZ echo or first flash occurs in the next 30 minutes.",
        "radar composite / ILLN",
    ),
    "ci_60": HazardDefinition(
        "ci_60",
        "First 35 dBZ echo or first flash occurs in the next 60 minutes.",
        "radar composite / ILLN",
    ),
    "hail": HazardDefinition(
        "hail",
        "Grade A or B hail report within 25 km and 45 minutes of an object.",
        "curated reports",
    ),
    "gust": HazardDefinition(
        "gust",
        "AWS gust at least 17 m/s within 30 minutes and 25 km, or IMD squall report.",
        "IMD AWS / reports",
    ),
    "cloudburst_point": HazardDefinition(
        "cloudburst_point",
        "Hourly gauge accumulation at least 100 mm.",
        "AWS / ARG hourly gauge",
    ),
    "cloudburst_area_proxy": HazardDefinition(
        "cloudburst_area_proxy",
        "HEM and radar estimate at least 100 mm/h over at least five contiguous 2 km cells.",
        "HEM / radar composite",
        proxy=True,
    ),
}
