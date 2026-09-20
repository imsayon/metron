import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const e2ePort = process.env.METRON_E2E_PORT ?? "39123";

export default defineConfig({
  testDir: ".",
  testMatch: "**/*.spec.ts",
  // ponytail: serial smoke avoids cold Next dev-server contention; parallelize with a production server harness.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "dot" : "list",
  use: {
    baseURL: process.env.BASE_URL ?? "http://127.0.0.1:" + e2ePort,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    channel: process.env.PLAYWRIGHT_CHANNEL ?? "chrome",
    ...devices["Desktop Chrome"]
  },
  webServer: {
    command: "./node_modules/.bin/next dev --hostname 127.0.0.1 --port " + e2ePort,
    cwd: path.resolve(__dirname, "../../ui"),
    url: "http://127.0.0.1:" + e2ePort,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000
  }
});
