# Metron engineering instructions

Metron is an evidence-first material-identity project. Read the canonical documents in `imsayon/metron-docs` before making product or architecture changes, especially the SIH26099 problem statement, research brainstorm, product scope, architecture, and open decisions.

Keep exact identity, near-duplicate review, and functional equivalence as separate concepts. Do not turn a similarity score into an engineering approval. Preserve source-system identifiers and provenance. Treat missing attributes as unknown, not as agreement.

Keep model-generated extraction or explanations separate from deterministic conflict rules, evidence checks, mappings, and approvals. Do not add live SAP/ERP writes, procurement execution, autonomous approvals, or a new classification standard without an explicit decision recorded in the docs repository.

Inspect status before editing, preserve unrelated work, and validate the actual final state. Do not commit secrets, raw confidential CPSE data, or claims that have not been verified.

Claude and Codex are working together through a human-reviewed handoff. Claude owns research/product review in the working agreement; Codex owns implementation, tests, and local verification in this repository.

