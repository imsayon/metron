import type { FixtureInput, FixtureProvenance } from "../lib/fixtures";

export function ProvenanceChips({
  provenance,
  compact = false
}: {
  provenance: FixtureProvenance;
  compact?: boolean;
}) {
  return (
    <div className={compact ? "provenance compact" : "provenance"} data-testid="provenance-chips">
      <span className="chip chip-accent">{provenance.rung} rung</span>
      <span className="chip">Tier {provenance.tier}</span>
      <span className="chip">{provenance.leadMin} min lead</span>
      <span className="chip chip-muted">model {provenance.modelVersion}</span>
      <span className="chip chip-muted">{provenance.skillRef ? provenance.skillRef : "skill UNKNOWN"}</span>
    </div>
  );
}

export function SourceChips({ inputs }: { inputs: FixtureInput[] }) {
  return (
    <div className="source-strip" aria-label="Source ages">
      {inputs.map((input) => (
        <span
          className={"source-chip " + (input.available ? "source-ok" : "source-missing")}
          key={input.source}
          data-testid={"source-chip-" + input.source}
        >
          <span aria-hidden="true">{input.available ? "●" : "×"}</span>
          {input.label} {input.ageMin === null ? "—" : String(input.ageMin) + "m"}
          {!input.calibrated && <em>uncal</em>}
        </span>
      ))}
    </div>
  );
}
