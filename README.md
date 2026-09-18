# Metron

Metron is an AI-assisted material-identity and data-governance platform for SIH26099: the National Unified Material Master problem. It is intended to help participating CPSEs discover duplicate and near-duplicate material records, preserve source-system mappings, surface evidence, and route uncertain decisions to material specialists.

This repository is the implementation end. The canonical product, research, architecture, and governance documents live in the private [`imsayon/metron-docs`](https://github.com/imsayon/metron-docs) repository.

## Claude and Codex working together

Claude and Codex are working together on Metron through a human-orchestrated handoff:

- Claude end: research synthesis, product framing, architecture critique, and document review.
- Codex end: repository initialization, implementation, tests, local verification, and release hygiene.

This README is written from the Codex end. The division describes responsibility; it does not imply an automated connection between the two model sessions.

## Current status

The repository has been initialized with the project boundary and developer handoff documents. Product implementation has not been claimed yet. The next engineering step is to agree on the identity semantics, initial material categories, source data contract, and evaluation labels before building a matcher.

## Repository map

- [`docs/`](docs/README.md): implementation-facing notes and links to canonical documentation.
- [`AGENTS.md`](AGENTS.md): working rules for future engineering agents.
- [`metron-docs`](https://github.com/imsayon/metron-docs): research and product source of truth.

## Problem boundary

Metron must distinguish, with evidence:

1. Exact or duplicate material identity.
2. Near-duplicate records that need review.
3. Functionally equivalent or conditionally substitutable materials.
4. Records that cannot be safely compared because required attributes are missing.

Text similarity is a candidate-discovery signal. It is not, by itself, proof of identity or interchangeability. The system must preserve source records, show conflicting and missing attributes, support human approval, and never invent a golden specification by combining unsupported values.

## Source status

The SIH26099 problem statement and the research notes are copied into `metron-docs` with provenance. Dataset availability, sponsor labels, common-code semantics, classification standard, and live SAP/ERP access remain open questions.

## License

No license has been selected yet. Do not assume that this repository may be reused or redistributed until the project owner adds one.

