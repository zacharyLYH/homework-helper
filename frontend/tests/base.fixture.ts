import { expect, test as base } from "@playwright/test";
import { initMockBackend, DEFAULT_STREAM } from "./helpers/stream";

// Test harness default: a logged-in app over a fully mocked backend.
//
// The whole backend lives in one window.fetch override (installed as an init
// script via helpers/stream.ts) that serves every /api call from canned JSON
// plus a real streaming body for /api/chat/stream. page.route is deliberately
// not used here: the app's data calls go through the same overridden fetch, so
// there is one source of truth and nothing to keep in sync.
// Per-test `stubStream`/`captureStream` swap the streamed reply mid-page.
type AuthMode = "authenticated" | "none";

export const test = base.extend<{ auth: AuthMode }>({
  auth: ["authenticated", { option: true }],
  page: async ({ page, auth }, use) => {
    await initMockBackend(page, { auth: auth === "authenticated", defaultSpec: DEFAULT_STREAM });
    await use(page);
  },
});

export { expect };