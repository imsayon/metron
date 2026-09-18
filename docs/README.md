# Metron implementation documents

This folder contains documents that help the implementation team work against the canonical research and product decisions.

The source of truth for research, scope, architecture decisions, evaluation, and governance is the private [`imsayon/metron-docs`](https://github.com/imsayon/metron-docs) repository. Keep implementation-specific notes here only when they belong with code and link back to the canonical document.

## Current documents

- [`DEVELOPMENT.md`](DEVELOPMENT.md): repository workflow and current initialization state.

The runtime architecture has not been selected yet. The first implementation must follow the decision records in `metron-docs`, rather than silently assuming a vector database, taxonomy, LLM, or SAP integration.

