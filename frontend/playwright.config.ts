import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  use: {
    baseURL: "http://localhost:4173",
    viewport: { width: 1280, height: 720 },
    screenshot: "only-on-failure",
  },
  // A few percent of differing pixels are tolerated so screenshots hold up
  // across OSes with font metric differences; the point of the visual suite
  // is responsive design, not pixel-perfect fonts.
  expect: {
    timeout: 5_000,
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.05,
      animations: "disabled",
    },
  },
  // Drop the browser + platform suffix so baselines are named identically on
  // every OS and in CI (e.g. "light-chat-messages-phone.png", no
  // "-chromium-darwin"). maxDiffPixelRatio absorbs the rendering differences.
  snapshotPathTemplate: "{testDir}/{testFilePath}-snapshots/{arg}{ext}",
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 720 } } }],
  webServer: {
    command: "npm run preview -- --port 4173",
    url: "http://localhost:4173",
    reuseExistingServer: !process.env.CI,
  },
});