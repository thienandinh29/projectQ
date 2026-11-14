import { defineConfig, devices } from "@playwright/test";

// Browser tests of the English pack against a running stack (specs/web-english, 1.4b).
// Start the stack first (docker compose up), with DRAFT_ITEM_LEARNERS set to E2E_LEARNER_ID.
export default defineConfig({
  testDir: "e2e",
  timeout: 90_000,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "off",
    ...devices["Pixel 7"], // phone first
  },
});
