# Development handoff

## Before implementation

1. Read `metron-docs/docs/product/PRODUCT-SCOPE.md`.
2. Read `metron-docs/docs/architecture/ARCHITECTURE.md`.
3. Read `metron-docs/docs/product/OPEN-DECISIONS.md`.
4. Confirm the source-data contract and evaluation labels.
5. Record any changed decision in the docs repository before building against it.

## Evidence and claims

Every matcher result must preserve source records, extracted attributes, conflicts, missing evidence, and the rule/model path that produced the recommendation. Scores are scores unless calibrated against representative labels. Synthetic data can validate behavior and failure handling; it cannot establish industrial accuracy or procurement savings.

## Collaboration

Claude and Codex work from the same documented decisions. Claude reviews research, scope, and architecture. Codex implements the repository, runs tests, and verifies the local product. Human review remains required for material identity, functional equivalence, common-code approval, and any external integration.

## Current initialization state

The repository is initialized for implementation but contains no production matcher yet. The first code milestone is a reproducible fixture and data contract, followed by category-aware normalization and candidate retrieval.

