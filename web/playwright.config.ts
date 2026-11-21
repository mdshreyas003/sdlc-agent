import { defineConfig } from "@playwright/test";

// Accessibility checks run against a production build, the same way ArgosX scans the live site.
export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  use: { baseURL: "http://localhost:3979" },
  webServer: { command: "npm run build && npm run start -- -p 3979", url: "http://localhost:3979/login", timeout: 300_000, reuseExistingServer: true },
});
