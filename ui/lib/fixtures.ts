export type Rung = "R0" | "R1" | "R2" | "R3" | "R4";
export type Tier = "A" | "B" | "C";

export const AVAILABLE_LEADS = [15, 30, 60, 120, 180] as const;

export type FixtureInput = {
  source: string;
  label: string;
  ageMin: number | null;
  available: boolean;
  calibrated: boolean;
};

export type FixtureProvenance = {
  domain: string;
  issueTime: string;
  validTime: string;
  leadMin: number;
  tier: Tier;
  rung: Rung;
  mode: "live" | "replay";
  modelVersion: string;
  calibrationId: string | null;
  skillRef: string | null;
  inputs: FixtureInput[];
  watermark: string;
};

export const MOCK_API_FIXTURE = {
  synthetic: true,
  label: "fixture-day / synthetic / non-citable",
  provenance: {
    domain: "pilot_e",
    issueTime: "2026-05-03T09:30:00Z",
    validTime: "2026-05-03T10:00:00Z",
    leadMin: 30,
    tier: "A" as Tier,
    rung: "R1" as Rung,
    mode: "live" as const,
    modelVersion: "M2-fixture-not-for-release",
    calibrationId: null,
    skillRef: null,
    inputs: [
      { source: "insat_browse", label: "INSAT-3DS IR1", ageMin: 15, available: true, calibrated: false },
      { source: "radar", label: "Radar mosaic", ageMin: null, available: false, calibrated: false },
      { source: "illn", label: "ILLN lightning", ageMin: 1, available: true, calibrated: false },
      { source: "gfs", label: "GFS 00Z", ageMin: 570, available: true, calibrated: true }
    ],
    watermark: "EXPERIMENTAL GUIDANCE — NOT AN OFFICIAL IMD WARNING"
  } satisfies FixtureProvenance,
  products: [
    { id: "ltg_prob", label: "Lightning probability", color: "#ffbc42", research: true },
    { id: "ci_prob", label: "Convective initiation", color: "#e8f34a", research: true },
    { id: "rain_prob", label: "Rain probability", color: "#70c7ff", research: true },
    { id: "hail_prob", label: "Hail probability", color: "#ff8066", research: true }
  ],
  objects: [
    {
      trackId: "pe-20260503-0412",
      state: "mature",
      ageMin: 50,
      centroid: "87.20°E, 23.30°N",
      zmax: "52.5 dBZ",
      ltgRate: "3.2 / min",
      polygon: "320,175 410,145 490,180 470,260 385,275 305,235"
    },
    {
      trackId: "pe-20260503-0407",
      state: "growing",
      ageMin: 25,
      centroid: "87.65°E, 23.05°N",
      zmax: "44.1 dBZ",
      ltgRate: "1.1 / min",
      polygon: "515,300 580,260 655,285 645,350 560,365"
    }
  ],
  targets: [
    { id: "VECC", name: "Kolkata / NSCBI", kind: "airport", x: 490, y: 220, radiusKm: 15 },
    { id: "BANKURA-HOSP", name: "Bankura Sammilani Hospital", kind: "critical site", x: 585, y: 320, radiusKm: 5 }
  ],
  arrival: {
    targetName: "Kolkata / NSCBI",
    targetId: "VECC",
    pArrival: 0.71,
    t10Min: 35,
    t50Min: 52,
    t90Min: 80,
    pDecay: 0.18,
    synthetic: true
  },
  abstentions: [
    { module: "M5 downburst", reason: "no_velocity", detail: "Radar radial velocity is unavailable this cycle." },
    { module: "M4 hail", reason: "no_radar", detail: "Hail guidance is research-badged while radar is absent." }
  ],
  verification: {
    state: "unknown" as const,
    detail: "F4 verification API is not merged; synthetic fixture scores are non-citable.",
    frozenFigureId: null
  },
  review: {
    alertId: "metron-pilot_e-fixture-001",
    status: "Test" as const,
    hazard: "Lightning nowcast guidance",
    target: "Kolkata / NSCBI",
    delivery: "disabled in fixture mode"
  }
} as const;
