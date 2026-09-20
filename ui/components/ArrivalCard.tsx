import type { MOCK_API_FIXTURE } from "../lib/fixtures";

type Arrival = typeof MOCK_API_FIXTURE.arrival;

function toClock(minutes: number) {
  const baseHour = 9;
  const baseMinute = 30 + minutes;
  const hour = baseHour + Math.floor(baseMinute / 60);
  const minute = baseMinute % 60;
  return String(hour).padStart(2, "0") + ":" + String(minute).padStart(2, "0") + "Z";
}

export function ArrivalCard({ arrival }: { arrival: Arrival }) {
  return (
    <section className="arrival-card" data-testid="arrival-card" aria-labelledby="arrival-heading">
      <div className="section-kicker">Arrival window · synthetic fixture</div>
      <div className="arrival-heading-row">
        <h3 id="arrival-heading">{arrival.targetName}</h3>
        <span className="probability" data-testid="arrival-probability">
          P {arrival.pArrival.toFixed(2)}
        </span>
      </div>
      <div className="arrival-window" data-testid="arrival-window">
        <span className="arrival-endpoint">
          <b>T10</b>
          {toClock(arrival.t10Min)}
        </span>
        <div className="arrival-bar" aria-label={"Arrival window from " + toClock(arrival.t10Min) + " to " + toClock(arrival.t90Min)}>
          <span className="arrival-fill" style={{ left: "8%", width: "73%" }} />
          <i className="arrival-tick" style={{ left: "36%" }} aria-label={"T50 " + toClock(arrival.t50Min)} />
        </div>
        <span className="arrival-endpoint">
          <b>T90</b>
          {toClock(arrival.t90Min)}
        </span>
      </div>
      <div className="arrival-meta">
        <span>T50 {toClock(arrival.t50Min)}</span>
        <span>P(decay before T50) {arrival.pDecay.toFixed(2)}</span>
      </div>
      <p className="fixture-note">Window required. There is no standalone ETA control.</p>
    </section>
  );
}
