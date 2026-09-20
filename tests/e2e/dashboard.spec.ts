import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("keeps the experimental warning and provenance visible", async ({ page }) => {
  await expect(page.getByTestId("watermark")).toHaveText("EXPERIMENTAL GUIDANCE — NOT AN OFFICIAL IMD WARNING");
  await expect(page.getByTestId("provenance-chips").first()).toContainText("R1 rung");
  await expect(page.getByTestId("source-chip-radar")).toContainText("×");
  await expect(page.getByTestId("source-chip-radar")).toContainText("Radar mosaic");
});

test("snaps the lead control to available leads and updates the tier", async ({ page }) => {
  await page.getByRole("button", { name: "120" }).click();
  await expect(page.locator(".lead-section .section-heading strong")).toHaveText("120 min");
  await expect(page.getByText("Tier B", { exact: true }).first()).toBeVisible();
  await expect(page.getByTestId("provenance-chips").first()).toContainText("R2 rung");
});

test("target toggles control target overlays without changing the fixture", async ({ page }) => {
  await expect(page.getByTestId("target-VECC")).toBeVisible();
  await page.getByTestId("target-toggle-VECC").click();
  await expect(page.getByTestId("target-VECC")).toHaveCount(0);
});

test("renders an arrival window instead of a standalone ETA", async ({ page }) => {
  const card = page.getByTestId("arrival-card");
  await expect(card).toContainText("T10");
  await expect(card).toContainText("T50");
  await expect(card).toContainText("T90");
  await expect(card.getByTestId("arrival-probability")).toHaveText("P 0.71");
  await expect(card).toContainText("Window required");
});

test("keeps abstention and replay degradation visible", async ({ page }) => {
  await expect(page.getByTestId("abstention").first()).toContainText("no_velocity");
  await page.getByTestId("replay-toggle").click();
  await expect(page.getByTestId("replay-watermark")).toContainText("REPLAY");
  await expect(page.getByTestId("replay-virtual-clock")).toHaveText("virtual clock active");
});

test("verification reports unknown instead of inventing a score", async ({ page }) => {
  await page.getByTestId("verification-open").click();
  const drawer = page.getByTestId("verification-drawer");
  await expect(drawer).toContainText("UNKNOWN");
  await expect(drawer).toContainText("Metric values are intentionally not fabricated.");
});

test("CAP approval is gated by an explicit human review", async ({ page }) => {
  await page.getByTestId("cap-draft").click();
  const panel = page.getByTestId("cap-review");
  const approve = panel.getByTestId("cap-approve");
  await expect(approve).toBeDisabled();
  await expect(panel).toContainText("No autonomous approval");
  await panel.getByText(/I am the authorized human forecaster reviewing/).click();
  await expect(approve).toBeEnabled();
  await approve.click();
  await expect(approve).toHaveText("Human-approved / local only");
});
