import { test, expect } from "../base.fixture";
import type { Page } from "@playwright/test";
import { GOOD, MEMORY, measureTransition, readMemory, type Vitals } from "./vitals";

function report(name: string, v: Vitals) {
  console.log(`${name} → LCP ${v.lcp.toFixed(0)}ms / FCP ${v.fcp.toFixed(0)}ms / CLS ${v.cls.toFixed(3)}`);
}

function assertGood(name: string, v: Vitals) {
  report(name, v);
  expect(v.lcp, `LCP ${v.lcp.toFixed(0)}ms should be ≤ ${GOOD.lcpMs}ms`).toBeLessThanOrEqual(GOOD.lcpMs);
  expect(v.fcp, `FCP ${v.fcp.toFixed(0)}ms should be ≤ ${GOOD.fcpMs}ms`).toBeLessThanOrEqual(GOOD.fcpMs);
  expect(v.cls, `CLS ${v.cls.toFixed(3)} should be ≤ ${GOOD.cls}`).toBeLessThanOrEqual(GOOD.cls);
}

async function assertMemoryGood(name: string, page: Page) {
  const mem = await readMemory(page);
  const heapMb = mem.heapBytes / 1024 / 1024;
  console.log(`${name} → heap ${heapMb.toFixed(1)}MB / DOM ${mem.domCount}`);
  expect(heapMb, `${name} heap ${heapMb.toFixed(1)}MB should be ≤ ${MEMORY.heapMb}MB`).toBeLessThanOrEqual(
    MEMORY.heapMb,
  );
  expect(mem.domCount, `${name} DOM ${mem.domCount} should be ≤ ${MEMORY.domCount}`).toBeLessThanOrEqual(
    MEMORY.domCount,
  );
}

async function loadCheck(page: Page, path: string, name: string) {
  const v = await measureTransition(page, path);
  assertGood(name, v);
  await assertMemoryGood(name, page);
}

test("chat: LCP, CLS and memory within bounds on load", async ({ page }) => {
  await loadCheck(page, "/chat", "chat");
});

test("whiteboard: LCP, CLS and memory within bounds on load", async ({ page }) => {
  await loadCheck(page, "/whiteboard?chatId=10", "whiteboard");
});

test.describe("unauthenticated", () => {
  test.use({ auth: "none" });

  test("login: LCP, CLS and memory within bounds on load", async ({ page }) => {
    await loadCheck(page, "/login", "login");
  });
});
