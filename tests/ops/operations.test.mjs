import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const read = (name) => fs.readFileSync(path.join(root, name), "utf8");

test("gateway config preserves security headers and API routing", () => {
  const caddy = read("deploy/Caddyfile");
  assert.match(caddy, /X-Content-Type-Options/);
  assert.match(caddy, /Content-Security-Policy/);
  assert.doesNotMatch(caddy, /unsafe-eval/);
  assert.match(caddy, /reverse_proxy @api api:8000/);
  assert.match(caddy, /reverse_proxy ui:3000/);
});

test("Prometheus config scrapes API and tile metrics", () => {
  const prometheus = read("deploy/prometheus.yml");
  assert.match(prometheus, /job_name: metron-api/);
  assert.match(prometheus, /job_name: metron-titiler/);
  assert.match(prometheus, /metrics_path: \/metrics/);
});

test("alert rules cover stale inputs, overruns, degradation, and CAP failures", () => {
  const alerts = read("deploy/alerts.yml");
  for (const alert of ["MetronSourceStale", "MetronCycleOverrun", "MetronRungDegraded", "MetronCapDeliveryFailure"]) {
    assert.match(alerts, new RegExp("alert: " + alert));
  }
  assert.match(alerts, /Do not retry automatically/);
});

test("Grafana dashboard contains operational panels", () => {
  const dashboard = JSON.parse(read("deploy/grafana/dashboards/operations.json"));
  const titles = dashboard.panels.map((panel) => panel.title);
  assert.deepEqual(titles, ["Current rung", "Cycle latency p95", "Source ages", "Abstentions by reason", "CAP delivery failures"]);
});
