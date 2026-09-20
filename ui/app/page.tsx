"use client";

import { useState } from "react";
import { ArrivalCard } from "../components/ArrivalCard";
import { ProvenanceChips, SourceChips } from "../components/ProvenanceChips";
import { AVAILABLE_LEADS, MOCK_API_FIXTURE, type Rung, type Tier } from "../lib/fixtures";

type LayerId = "satellite" | "radar" | "lightning" | "nwp";
type ReplayState = "idle" | "running" | "paused";

const LAYERS: Array<{ id: LayerId; label: string; detail: string }> = [
  { id: "satellite", label: "Sat IR1", detail: "brightness temperature" },
  { id: "radar", label: "Radar Zmax", detail: "missing in fixture" },
  { id: "lightning", label: "Lightning", detail: "flash density" },
  { id: "nwp", label: "NWP CAPE", detail: "environment context" }
];

function tierForLead(lead: number): Tier {
  if (lead <= 60) return "A";
  if (lead <= 180) return "B";
  return "C";
}

function rungForFixture(lead: number): Rung {
  return lead > 60 ? "R2" : MOCK_API_FIXTURE.provenance.rung;
}

function MapCanvas({
  activeLayers,
  selectedTrack,
  selectedProduct,
  visibleTargets,
  onSelectTrack
}: {
  activeLayers: Record<LayerId, boolean>;
  selectedTrack: string;
  selectedProduct: string;
  visibleTargets: Record<string, boolean>;
  onSelectTrack: (trackId: string) => void;
}) {
  const selectedColor = MOCK_API_FIXTURE.products.find((product) => product.id === selectedProduct)?.color ?? "#ffbc42";

  return (
    <div className="map-frame" data-testid="map-canvas">
      <div className="map-label">
        <span className="section-kicker">Pilot-E / 2 km LCC</span>
        <strong>Convective field</strong>
      </div>
      <svg viewBox="0 0 780 470" role="img" aria-label="Pilot-E hazard map with storm objects and critical targets">
        <defs>
          <pattern id="map-grid" width="42" height="42" patternUnits="userSpaceOnUse">
            <path d="M 42 0 L 0 0 0 42" fill="none" stroke="#2a3940" strokeWidth="1" />
          </pattern>
          <filter id="soft-glow">
            <feGaussianBlur stdDeviation="8" />
          </filter>
        </defs>
        <rect width="780" height="470" fill="#101c21" />
        <rect width="780" height="470" fill="url(#map-grid)" opacity="0.7" />
        <path
          d="M40 105 C140 70 160 145 255 112 S385 70 458 125 S620 180 745 120 M40 390 C150 330 230 400 315 354 S505 310 740 380"
          fill="none"
          stroke="#32474c"
          strokeWidth="2"
          strokeDasharray="5 9"
        />
        <path d="M82 36 L160 80 L140 152 L198 216 L170 295 L235 358 L205 430" fill="none" stroke="#405b5e" strokeWidth="2" />
        <path d="M655 20 L612 104 L655 160 L605 230 L632 302 L580 390 L615 450" fill="none" stroke="#405b5e" strokeWidth="2" />

        {activeLayers.satellite && (
          <g aria-label="Satellite IR1 layer" data-testid="map-layer-satellite">
            <circle cx="360" cy="210" r="105" fill="#a0b8be" opacity="0.08" filter="url(#soft-glow)" />
            <circle cx="425" cy="230" r="86" fill="#dce9e7" opacity="0.1" />
            <circle cx="300" cy="245" r="65" fill="#829a9b" opacity="0.1" />
            <text x="26" y="34" className="map-layer-caption">SAT IR1 / UNCAL</text>
          </g>
        )}
        {activeLayers.radar && (
          <g aria-label="Radar layer" data-testid="map-layer-radar">
            <path d="M250 190 L455 120 L545 230 L480 312 L270 285 Z" fill="#ff8066" opacity="0.16" />
            <text x="26" y="54" className="map-layer-caption warning">RADAR / 0 OF 6</text>
          </g>
        )}
        {activeLayers.lightning && (
          <g aria-label="Lightning layer" data-testid="map-layer-lightning">
            {[
              [350, 162],
              [390, 205],
              [430, 186],
              [414, 247],
              [465, 222],
              [580, 306],
              [610, 326]
            ].map(([x, y]) => (
              <path key={x + "-" + y} d={"M" + x + " " + (y - 10) + " l-8 13 h7 l-6 14 15-18 h-8z"} fill="#e8f34a" />
            ))}
            <text x="26" y="74" className="map-layer-caption">ILLN / 1M AGE</text>
          </g>
        )}
        {activeLayers.nwp && (
          <g aria-label="NWP CAPE layer" data-testid="map-layer-nwp">
            <ellipse cx="590" cy="145" rx="130" ry="54" fill="#70c7ff" opacity="0.1" />
            <text x="26" y="94" className="map-layer-caption">GFS / 00Z</text>
          </g>
        )}

        <polygon
          points="285,150 455,125 530,215 490,300 345,300 270,230"
          fill={selectedColor}
          opacity="0.07"
          stroke={selectedColor}
          strokeDasharray="6 5"
        />
        {MOCK_API_FIXTURE.targets.filter((target) => visibleTargets[target.id]).map((target) => (
          <g key={target.id} data-testid={"target-" + target.id}>
            <circle cx={target.x} cy={target.y} r={target.kind === "airport" ? 29 : 17} fill="none" stroke="#e8f34a" strokeOpacity="0.35" strokeDasharray="3 5" />
            <circle cx={target.x} cy={target.y} r="4" fill="#e8f34a" />
            <text x={target.x + 10} y={target.y - 8} className="target-label">{target.id}</text>
          </g>
        ))}
        {MOCK_API_FIXTURE.objects.map((object) => {
          const selected = object.trackId === selectedTrack;
          return (
            <g
              key={object.trackId}
              data-testid="map-object-track"
              className={selected ? "map-object selected" : "map-object"}
              role="button"
              tabIndex={0}
              aria-label={"Inspect storm " + object.trackId}
              onClick={() => onSelectTrack(object.trackId)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") onSelectTrack(object.trackId);
              }}
            >
              <polygon points={object.polygon} fill={selected ? selectedColor : "#70c7ff"} opacity={selected ? "0.34" : "0.16"} stroke={selected ? selectedColor : "#70c7ff"} strokeWidth={selected ? "3" : "1.5"} />
              <circle cx={selected ? 400 : 590} cy={selected ? 215 : 315} r="5" fill="#f8f4e8" />
              <text x={selected ? 320 : 520} y={selected ? 135 : 258} className="object-label">{object.trackId.slice(-5)}</text>
            </g>
          );
        })}
        <g className="map-scale">
          <path d="M32 426 h80" stroke="#f8f4e8" strokeWidth="2" />
          <text x="32" y="445">40 km</text>
        </g>
      </svg>
      <div className="map-legend">
        <span><i className="legend-dot lightning" /> Probability / {selectedProduct}</span>
        <span><i className="legend-line" /> Object polygon</span>
        <span><i className="legend-target" /> Target radius</span>
      </div>
    </div>
  );
}

function VerificationDrawer({ onClose }: { onClose: () => void }) {
  return (
    <aside className="verification-drawer" data-testid="verification-drawer" aria-labelledby="verification-heading">
      <div className="drawer-header">
        <div>
          <span className="section-kicker">Evidence / verification</span>
          <h2 id="verification-heading">No citable score in fixture mode</h2>
        </div>
        <button className="icon-button" type="button" onClick={onClose} aria-label="Close verification drawer">×</button>
      </div>
      <div className="unknown-panel">
        <strong>UNKNOWN</strong>
        <span>{MOCK_API_FIXTURE.verification.detail}</span>
      </div>
      <div className="drawer-controls">
        <label>Product<select defaultValue="ltg_prob"><option>ltg_prob</option><option>ci_prob</option><option>rain_prob</option></select></label>
        <label>Lead<select defaultValue="30"><option>15 min</option><option>30 min</option><option>60 min</option></select></label>
        <span className="chip chip-accent">R1</span>
      </div>
      <div className="empty-figure">
        <div className="empty-figure-grid"><span /><span /><span /><span /><span /></div>
        <p>Rolling and frozen figures appear here when the verification API supplies a verified run and figure ID.</p>
        <small>Metric values are intentionally not fabricated.</small>
      </div>
    </aside>
  );
}

export default function DashboardPage() {
  const [lead, setLead] = useState(30);
  const [selectedTrack, setSelectedTrack] = useState<string>(MOCK_API_FIXTURE.objects[0].trackId);
  const [selectedProduct, setSelectedProduct] = useState("ltg_prob");
  const [activeLayers, setActiveLayers] = useState<Record<LayerId, boolean>>({
    satellite: true,
    radar: false,
    lightning: true,
    nwp: false
  });
  const [visibleTargets, setVisibleTargets] = useState<Record<string, boolean>>({
    VECC: true,
    "BANKURA-HOSP": true
  });
  const [verificationOpen, setVerificationOpen] = useState(false);
  const [replayMode, setReplayMode] = useState(false);
  const [replayState, setReplayState] = useState<ReplayState>("idle");
  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewStatus, setReviewStatus] = useState<"Test" | "Actual">("Test");
  const [humanConfirmed, setHumanConfirmed] = useState(false);
  const [reviewNotes, setReviewNotes] = useState("");

  const tier = tierForLead(lead);
  const rung = rungForFixture(lead);
  const provenance = { ...MOCK_API_FIXTURE.provenance, leadMin: lead, tier, rung, mode: replayMode ? "replay" as const : "live" as const };
  const selectedObject = MOCK_API_FIXTURE.objects.find((object) => object.trackId === selectedTrack) ?? MOCK_API_FIXTURE.objects[0];
  const selectedProductInfo = MOCK_API_FIXTURE.products.find((product) => product.id === selectedProduct) ?? MOCK_API_FIXTURE.products[0];

  function setSnappedLead(value: number) {
    const next = AVAILABLE_LEADS.reduce((nearest, candidate) => (
      Math.abs(candidate - value) < Math.abs(nearest - value) ? candidate : nearest
    ), AVAILABLE_LEADS[0]);
    setLead(next);
  }

  function toggleReplay() {
    setReplayMode(true);
    setReplayState("running");
  }

  function stopReplay() {
    setReplayMode(false);
    setReplayState("idle");
  }

  return (
    <main className="dashboard-shell" data-testid="dashboard-shell">
      <header className="global-chrome">
        <div className="brand-lockup">
          <div className="brand-mark">M</div>
          <div>
            <div className="brand-name">METRON</div>
            <div className="brand-subtitle">convective guidance desk</div>
          </div>
        </div>
        <div className="domain-switcher">
          <span className="section-kicker">DOMAIN</span>
          <strong>pilot_e</strong>
          <span className="caret">▾</span>
        </div>
        <div className="mode-switcher" aria-label="Mode">
          <button className={!replayMode ? "mode active" : "mode"} type="button" onClick={stopReplay}>● LIVE</button>
          <button className={replayMode ? "mode active replay" : "mode"} type="button" onClick={toggleReplay} data-testid="replay-toggle">◌ REPLAY</button>
        </div>
        <div className="issue-stamp">
          <span className="section-kicker">ISSUE</span>
          <strong>{replayMode ? "virtual 09:30Z" : "09:30Z"}</strong>
          <span className="muted">2 min ago</span>
        </div>
        <button className="rung-button" type="button" title="R1 = satellite + lightning + NWP; radar is unavailable" data-testid="rung-chip">
          <span>RUNG</span>
          <strong>{rung}</strong>
          <small>ⓘ</small>
        </button>
        <button className="verification-button" type="button" onClick={() => setVerificationOpen(true)} data-testid="verification-open">
          <span className="verification-glyph">◎</span>
          Verification
          <span>↗</span>
        </button>
      </header>

      <div className="watermark-banner" data-testid="watermark">{MOCK_API_FIXTURE.provenance.watermark}</div>
      <div className="fixture-banner"><span>FIXTURE MODE</span> Mock API data because F4 is not merged · synthetic inputs · no live alerts · metrics non-citable</div>
      {replayMode && (
        <div className="replay-banner" data-testid="replay-watermark">
          <span>REPLAY</span> fixture-day · virtual 09:30Z · 10×
          <strong data-testid="replay-virtual-clock">virtual clock active</strong>
        </div>
      )}
      <SourceChips inputs={provenance.inputs} />

      <div className="workspace">
        <aside className="left-rail" aria-label="Layers and controls">
          <div className="rail-section">
            <div className="section-heading"><span className="section-kicker">LAYERS</span><span className="rail-count">04</span></div>
            <div className="layer-list">
              {LAYERS.map((layer) => (
                <label className="layer-row" key={layer.id}>
                  <input
                    type="checkbox"
                    checked={activeLayers[layer.id]}
                    onChange={() => setActiveLayers({ ...activeLayers, [layer.id]: !activeLayers[layer.id] })}
                    data-testid={"layer-" + layer.id}
                  />
                  <span className="custom-check" />
                  <span><strong>{layer.label}</strong><small>{layer.detail}</small></span>
                  {layer.id === "radar" && <em className="tiny-warning">off</em>}
                </label>
              ))}
            </div>
          </div>
          <div className="rail-section">
            <div className="section-heading"><span className="section-kicker">PRODUCT</span><span className="product-research">* experimental</span></div>
            <div className="product-list">
              {MOCK_API_FIXTURE.products.map((product) => (
                <button
                  className={selectedProduct === product.id ? "product-row active" : "product-row"}
                  key={product.id}
                  type="button"
                  onClick={() => setSelectedProduct(product.id)}
                >
                  <span className="product-dot" style={{ backgroundColor: product.color }} />
                  <span>{product.label}</span>
                  {product.research && <sup>*</sup>}
                </button>
              ))}
            </div>
          </div>
          <div className="rail-section lead-section">
            <div className="section-heading"><span className="section-kicker">LEAD</span><strong>{lead} min</strong></div>
            <input
              className="lead-slider"
              type="range"
              min="15"
              max="180"
              step="1"
              value={lead}
              onChange={(event) => setSnappedLead(Number(event.target.value))}
              list="lead-ticks"
              data-testid="lead-slider"
              aria-label="Forecast lead"
            />
            <datalist id="lead-ticks">{AVAILABLE_LEADS.map((value) => <option key={value} value={value} />)}</datalist>
            <div className="lead-ticks">{AVAILABLE_LEADS.map((value) => <button key={value} type="button" onClick={() => setLead(value)} className={lead === value ? "lead-tick active" : "lead-tick"}>{value}</button>)}</div>
            <div className="tier-readout"><span className={"tier-marker tier-" + tier.toLowerCase()}>Tier {tier}</span><span>rung {rung}</span></div>
            {tier !== "A" && <p className="tier-note">Beyond Tier A: blended / NWP-driven layers are shown with reduced confidence.</p>}
          </div>
          <div className="rail-section">
            <div className="section-heading"><span className="section-kicker">TARGETS</span><span className="rail-count">02</span></div>
            {MOCK_API_FIXTURE.targets.map((target) => (
              <label className="target-row" key={target.id} data-testid={"target-toggle-" + target.id}>
                <input
                  type="checkbox"
                  checked={visibleTargets[target.id]}
                  onChange={() => setVisibleTargets({ ...visibleTargets, [target.id]: !visibleTargets[target.id] })}
                />
                <span>{target.name}</span>
                <small>{target.radiusKm} km</small>
              </label>
            ))}
          </div>
          <div className="rail-footer">
            <ProvenanceChips provenance={provenance} compact />
            <span className="attribution">Map geometry: fixture schematic · analysis grid not resampled</span>
          </div>
        </aside>

        <section className="map-column" aria-label="Hazard map">
          <div className="map-toolbar">
            <div><span className="section-kicker">MAP / {selectedProductInfo.id}</span><strong>{selectedProductInfo.label}</strong></div>
            <div className="toolbar-status"><span className="status-dot" /> source age aware <span className="divider" /> 2 km analysis grid</div>
          </div>
          <MapCanvas activeLayers={{ ...activeLayers, radar: activeLayers.radar && provenance.inputs.some((input) => input.source === "radar" && input.available) }} selectedTrack={selectedTrack} selectedProduct={selectedProduct} visibleTargets={visibleTargets} onSelectTrack={setSelectedTrack} />
          <div className="timeline">
            <span className="section-kicker">TIMELINE</span>
            <button type="button" className="timeline-button" onClick={() => setLead(Math.max(15, lead - 15))}>◀</button>
            <span className="timeline-time">08:00</span>
            <div className="timeline-track"><span className="timeline-past" /><i style={{ left: lead > 60 ? "64%" : "42%" }} /><span className="timeline-issue">09:30Z</span></div>
            <span className="timeline-time">+6h</span>
            <button type="button" className="timeline-button" onClick={() => setLead(Math.min(180, lead + 15))}>▶</button>
            <button type="button" className={replayState === "running" ? "play-button running" : "play-button"} onClick={() => {
              setReplayMode(true);
              setReplayState(replayState === "running" ? "paused" : "running");
            }}>{replayState === "running" ? "Ⅱ pause" : "▶ play"}</button>
            <button type="button" className="replay-control" onClick={toggleReplay}>⟲ replay</button>
          </div>
        </section>

        <aside className="inspector" aria-label="Object inspector">
          <div className="inspector-heading">
            <div><span className="section-kicker">OBJECT INSPECTOR</span><h2>{selectedObject.trackId}</h2></div>
            <span className="state-badge">{selectedObject.state}</span>
          </div>
          <div className="object-facts">
            <span><b>age</b>{selectedObject.ageMin} min</span>
            <span><b>centroid</b>{selectedObject.centroid}</span>
            <span><b>Zmax</b>{selectedObject.zmax} <em>↑ 1.5 / 10m</em></span>
            <span><b>ltg</b>{selectedObject.ltgRate} <em>↑</em></span>
          </div>
          <ArrivalCard arrival={MOCK_API_FIXTURE.arrival} />
          <section className="hazard-section">
            <div className="section-kicker">HAZARDS / PRODUCT STATE</div>
            <div className="hazard-row"><span>hail</span><strong>0.32</strong><em className="research-badge">experimental</em></div>
            <div className="hazard-row abstain" data-testid="abstention"><span>downburst</span><strong>— abstain</strong><small>no_velocity</small></div>
          </section>
          <section className="abstention-list">
            <div className="section-kicker">ABSTENTIONS / {MOCK_API_FIXTURE.abstentions.length}</div>
            {MOCK_API_FIXTURE.abstentions.map((item) => (
              <div className="abstention-item" key={item.module} data-testid="abstention">
                <span className="abstain-icon">!</span>
                <div><strong>{item.module}</strong><small>{item.reason}</small><p>{item.detail}</p></div>
              </div>
            ))}
          </section>
          <div className="inspector-footer"><ProvenanceChips provenance={provenance} /></div>
        </aside>
      </div>

      <section className="bottom-dock">
        <div className="review-queue">
          <div className="dock-title"><span className="section-kicker">REVIEW QUEUE</span><span className="queue-count">1</span><small>CAP remains Test until a forecaster approves</small></div>
          <div className="review-card">
            <div className="review-card-main"><span className="review-status">{reviewStatus}</span><div><strong>Lightning / Kolkata NSCBI</strong><small>target set · {MOCK_API_FIXTURE.review.alertId}</small></div></div>
            <button className="outline-button" type="button" onClick={() => setReviewOpen(true)} data-testid="cap-draft">Draft CAP</button>
          </div>
        </div>
        <button className="verification-dock-button" type="button" onClick={() => setVerificationOpen(true)} data-testid="verification-dock">
          <span className="section-kicker">VERIFICATION DRAWER</span>
          <strong>Rolling 7d / frozen run</strong>
          <span className="unknown-inline">UNKNOWN · no F4 verification API</span>
          <span className="open-arrow">↗</span>
        </button>
      </section>

      {verificationOpen && <VerificationDrawer onClose={() => setVerificationOpen(false)} />}

      {reviewOpen && (
        <div className="modal-backdrop">
          <section className="review-panel" role="dialog" aria-modal="true" aria-labelledby="cap-review-heading" data-testid="cap-review">
            <div className="drawer-header">
              <div><span className="section-kicker">FORECASTER REVIEW / TEST CAP</span><h2 id="cap-review-heading">Draft CAP / {MOCK_API_FIXTURE.review.hazard}</h2></div>
              <button className="icon-button" type="button" onClick={() => setReviewOpen(false)} aria-label="Close CAP review">×</button>
            </div>
            <div className="cap-fields">
              <label>Identifier<input readOnly value={MOCK_API_FIXTURE.review.alertId} /></label>
              <label>Scope<select defaultValue="Restricted"><option>Restricted</option><option>Public</option></select></label>
              <label>Target<input readOnly value={MOCK_API_FIXTURE.review.target} /></label>
              <label>Status<input readOnly value={reviewStatus} /></label>
            </div>
            <div className="cap-preview">
              <div className="section-kicker">GENERATED EXPLANATION / NUMBERS CHECKED</div>
              <p>Lightning probability guidance for {MOCK_API_FIXTURE.review.target} in the window shown on the dashboard. <mark>P 0.71</mark> · <mark>T10–T90 window</mark>. This text is generated from the fixture product and carries the experimental watermark.</p>
              <small>CAP XML preview is local only. No delivery endpoint is connected.</small>
            </div>
            <label className="notes-field">Forecaster notes<textarea value={reviewNotes} onChange={(event) => setReviewNotes(event.target.value)} placeholder="Required for a review record" /></label>
            <label className="confirm-row">
              <input type="checkbox" checked={humanConfirmed} onChange={(event) => setHumanConfirmed(event.target.checked)} data-testid="cap-human-review" />
              <span>I am the authorized human forecaster reviewing this Test message. Approve locally for rehearsal only.</span>
            </label>
            <div className="review-actions">
              <button className="outline-button" type="button" onClick={() => setReviewOpen(false)}>Reject / close</button>
              <button
                className="primary-button"
                type="button"
                disabled={!humanConfirmed || reviewStatus === "Actual"}
                onClick={() => setReviewStatus("Actual")}
                data-testid="cap-approve"
              >
                {reviewStatus === "Actual" ? "Human-approved / local only" : "Approve Test message"}
              </button>
            </div>
            <div className="review-safety-note"><span>!</span> No autonomous approval, live alert, or external dispatch occurs in fixture mode. {MOCK_API_FIXTURE.review.delivery}.</div>
          </section>
        </div>
      )}
    </main>
  );
}
