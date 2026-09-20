"""CLI for human-curated label rows: ``add`` and ``grade``."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .catalogue import LabelCatalogue


def _catalogue(path: str) -> LabelCatalogue:
    file = Path(path)
    return LabelCatalogue.load_jsonl(file) if file.exists() else LabelCatalogue()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="metron labels")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add", help="validate and add one event JSON object")
    add.add_argument("--catalogue", required=True)
    add.add_argument("--event", required=True, help="path to one event JSON object")
    grade = commands.add_parser("grade", help="apply a curator grade to an event")
    grade.add_argument("--catalogue", required=True)
    grade.add_argument("--event-id", required=True)
    grade.add_argument("--grade", required=True, choices=("A", "B", "C"))
    grade.add_argument("--location-error-km", type=float)
    grade.add_argument("--time-error-min", type=float)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    catalogue = _catalogue(args.catalogue)
    if args.command == "add":
        event = json.loads(Path(args.event).read_text(encoding="utf-8"))
        catalogue.add(event)
    else:
        catalogue.grade(
            args.event_id,
            args.grade,
            location_error_km=args.location_error_km,
            time_error_min=args.time_error_min,
        )
    catalogue.save_jsonl(args.catalogue)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
