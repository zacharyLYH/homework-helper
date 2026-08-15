import { expect, test as base } from "@playwright/test";
import { initMockBackend, DEFAULT_STREAM, DEFAULT_LLM_CONFIG, CATALOG } from "./helpers/stream";

// Test harness default: a logged-in app over a fully mocked backend.
//
// The whole backend lives in one window.fetch override (installed as an init
// script via helpers/stream.ts) that serves every /api call from canned JSON
// plus a real streaming body for /api/chat/stream. page.route is deliberately
// not used here: the app's data calls go through the same overridden fetch, so
// there is one source of truth and nothing to keep in sync.
// Per-test `stubStream`/`captureStream` swap the streamed reply mid-page.
type AuthMode = "authenticated" | "none";
type ThemeMode = "light" | "dark";

export const test = base.extend<{ auth: AuthMode; theme: ThemeMode }>({
  auth: ["authenticated", { option: true }],
  theme: ["dark", { option: true }],
  page: async ({ page, auth, theme }, use) => {
    await initMockBackend(page, {
      auth: auth === "authenticated",
      defaultSpec: DEFAULT_STREAM,
      defaultLlmConfig: DEFAULT_LLM_CONFIG,
      catalog: CATALOG,
    });
    // Pins the app theme (the app defaults to "dark" without this).
    await page.addInitScript((t) => localStorage.setItem("vite-ui-theme", t), theme);
    await use(page);
  },
});

export { expect };