import { test, expect } from "../base.fixture";
import type { Page } from "@playwright/test";
import { GOOD, installVitals, measureTransition, type Vitals } from "./vitals";

function report(name: string, v: Vitals) {
  console.log(`${name} → LCP ${v.lcp.toFixed(0)}ms / FCP ${v.fcp.toFixed(0)}ms / CLS ${v.cls.toFixed(3)}`);
}

function assertGood(name: string, v: Vitals) {
  report(name, v);
  expect(v.lcp, `LCP ${v.lcp.toFixed(0)}ms should be ≤ ${GOOD.lcpMs}ms`).toBeLessThanOrEqual(GOOD.lcpMs);
  expect(v.cls, `CLS ${v.cls.toFixed(3)} should be ≤ ${GOOD.cls}`).toBeLessThanOrEqual(GOOD.cls);
}

test("chat: LCP and CLS within Google 'good'", async ({ page }) => {
  assertGood("chat", await measureTransition(page, "/chat"));
});

test("whiteboard: LCP and CLS within Google 'good'", async ({ page }) => {
  assertGood("whiteboard", await measureTransition(page, "/whiteboard?chatId=10"));
});

test.describe("unauthenticated", () => {
  test.use({ auth: "none" });

  test("login: LCP and CLS within Google 'good'", async ({ page }) => {
    assertGood("login", await measureTransition(page, "/login"));
  });
});

test("chat: INP on real interactions within Google 'good'", async ({ page }) => {
  await installVitals(page);
  await page.goto("/chat");
  await page.waitForLoadState("load");
  await page.waitForFunction(() => (window.__vitals?.lcp ?? 0) > 0, undefined, { timeout: 10_000 });

  await page.getByRole("button", { name: "Algebra review" }).click();
  await page.getByRole("button", { name: "New Chat" }).first().click();
  await page.getByRole("button", { name: "Cancel" }).click();
  await page.getByRole("button", { name: "Algebra review" }).click();

  await page.waitForTimeout(1000);
  const v = (await page.evaluate(() => window.__vitals!))!;
  console.log(`chat → INP ${v.inp.toFixed(1)}ms`);
  expect(v.inp, `INP ${v.inp.toFixed(1)}ms should be ≤ ${GOOD.inpMs}ms`).toBeLessThanOrEqual(GOOD.inpMs);
});