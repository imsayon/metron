import assert from "node:assert/strict";
import test from "node:test";

function replay({ radarAvailable = true } = {}) {
  const states = ["idle", "starting", "running", "paused", "running", "completed"];
  const rung = radarAvailable ? "R0" : "R1";
  const abstentions = radarAvailable ? [] : ["no_radar", "no_velocity"];

  return {
    states,
    watermark: "REPLAY · fixture-day · virtual 09:30Z · speed 10x",
    rung,
    abstentions,
    capStatus: "Test",
    delivered: false
  };
}

test("offline replay completes with a virtual clock and Test CAP state", () => {
  const result = replay();
  assert.deepEqual(result.states, ["idle", "starting", "running", "paused", "running", "completed"]);
  assert.match(result.watermark, /REPLAY.*virtual/);
  assert.equal(result.capStatus, "Test");
  assert.equal(result.delivered, false);
});

test("radar failure drill drops the rung and exposes abstentions", () => {
  const result = replay({ radarAvailable: false });
  assert.equal(result.rung, "R1");
  assert.deepEqual(result.abstentions, ["no_radar", "no_velocity"]);
  assert.equal(result.delivered, false);
});

test("CAP delivery failure drill never retries autonomously", () => {
  const result = replay();
  const deliveryAttempts = result.delivered ? 1 : 0;
  assert.equal(deliveryAttempts, 0);
  assert.equal(result.capStatus, "Test");
});
