import { test, expect } from "../base.fixture";
import type { Page } from "@playwright/test";
import { GOOD, installVitals, readVitals, type Vitals } from "./vitals";

async function measureInteractions(name: string, page: Page) {
  await page.waitForTimeout(1000);
  const v = await readVitals(page);
  const inp = v.inp > 0 ? `${v.inp.toFixed(0)}ms` : "<16ms";
  console.log(`${name} → INP ${inp} / CLS ${v.cls.toFixed(3)}`);
  expect(v.inp, `INP ${inp} should be ≤ ${GOOD.inpMs}ms`).toBeLessThanOrEqual(GOOD.inpMs);
  expect(v.cls, `CLS ${v.cls.toFixed(3)} should be ≤ ${GOOD.cls}`).toBeLessThanOrEqual(GOOD.cls);
  return v;
}

test("chat: create subject through the dialog", async ({ page }) => {
  await installVitals(page);
  await page.goto("/chat");
  await page.waitForLoadState("load");
  await page.waitForFunction(() => (window.__vitals?.lcp ?? 0) > 0, undefined, { timeout: 10_000 });

  await page.getByRole("button", { name: "New Chat" }).first().click();
  await page.getByRole("tab", { name: "New Subject" }).click();
  await page.getByLabel("Subject Name").fill("Biology");
  await page.getByRole("button", { name: "Done" }).click();

  await measureInteractions("create subject", page);
});

test("chat: send a message and stream a reply", async ({ page }) => {
  await installVitals(page);
  await page.goto("/chat");
  await page.waitForLoadState("load");
  await page.waitForFunction(() => (window.__vitals?.lcp ?? 0) > 0, undefined, { timeout: 10_000 });

  await page.getByRole("button", { name: "Algebra review" }).click();
  await page.getByPlaceholder("Type your message...").fill("What is 2 + 2?");
  await page.locator('button[title="Send message"]').click();
  await expect(page.getByText("The answer is 4.")).toBeVisible();

  await measureInteractions("send message", page);
});

test.describe("unauthenticated", () => {
  test.use({ auth: "none" });

  test("login: client-side page navigation INP", async ({ page }: { page: Page }) => {
    await installVitals(page);
    await page.goto("/login");
    await page.waitForLoadState("load");

    // Login is fast enough that we need a couple of interactions for a meaningful INP.
    await page.getByLabel("Email").fill("test@example.com");
    await page.getByRole("button", { name: "Send code" }).click();
    await page.locator("input[autocomplete]").last().fill("123456");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/chat$/);

    await measureInteractions("login flow", page);
  });
});

test("whiteboard: tool switching INP", async ({ page }) => {
  await installVitals(page);
  await page.goto("/whiteboard?chatId=10");
  await page.waitForLoadState("load");
  await page.waitForFunction(() => (window.__vitals?.lcp ?? 0) > 0, undefined, { timeout: 10_000 });

  const tools = page.locator("button[aria-pressed]");
  const count = await tools.count();
  for (let i = 0; i < count; i++) {
    await tools.nth(i).click();
  }
  await page.locator('button[title="Clear canvas"]').click();

  await measureInteractions("tool switching", page);
});

test("whiteboard: draw a stroke, undo it, clear the canvas", async ({ page }) => {
  await installVitals(page);
  await page.goto("/whiteboard?chatId=10");
  await page.waitForLoadState("load");
  await page.waitForFunction(() => (window as any).__vitals?.lcp > 0, undefined, { timeout: 10_000 });

  const canvas = page.locator("canvas").first();
  const box = await canvas.boundingBox();
  if (!box) throw new Error("canvas has no bounding box");
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;

  await page.mouse.move(cx - 120, cy);
  await page.mouse.down();
  for (let i = 1; i <= 8; i++) {
    await page.mouse.move(cx - 120 + i * 30, cy + Math.sin(i) * 60);
  }
  await page.mouse.up();

  await page.locator('button[title="Undo"]').click();
  await page.locator('button[title="Clear canvas"]').click();

  await measureInteractions("whiteboard draw", page);
});