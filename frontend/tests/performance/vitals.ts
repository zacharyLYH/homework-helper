import type { Page } from "@playwright/test";

export const GOOD = { lcpMs: 2500, cls: 0.1, inpMs: 200 } as const;

export interface Vitals {
  lcp: number;
  cls: number;
  inp: number;
  fcp: number;
}

declare global {
  interface Window {
    __vitals?: Vitals;
  }
}

export async function installVitals(page: Page) {
  await page.addInitScript(() => {
    const v: Vitals = { lcp: 0, cls: 0, inp: 0, fcp: 0 };
    window.__vitals = v;

    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) {
        if (e.entryType === "largest-contentful-paint") v.lcp = e.startTime;
        if (e.entryType === "paint" && e.name === "first-contentful-paint") v.fcp = e.startTime;
      }
    }).observe({ type: "largest-contentful-paint", buffered: true });

    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) {
        if (e.entryType === "layout-shift") {
          const shift = e as { hadRecentInput?: boolean; value?: number };
          if (!shift.hadRecentInput && shift.value != null) v.cls += shift.value;
        }
      }
    }).observe({ type: "layout-shift", buffered: true });

    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) {
        if (e.entryType === "event" && e.duration >= 16) v.inp = Math.max(v.inp, e.duration);
      }
    }).observe(({ type: "event", buffered: true, durationThreshold: 16 } as unknown) as PerformanceObserverInit);
  });
}

export async function readVitals(page: Page): Promise<Vitals> {
  return page.evaluate(() => window.__vitals ?? { lcp: 0, cls: 0, inp: 0, fcp: 0 });
}

export async function measureTransition(page: Page, path: string): Promise<Vitals> {
  await installVitals(page);
  await page.goto(path);
  await page.waitForLoadState("load");
  await page.waitForFunction(() => (window.__vitals?.lcp ?? 0) > 0, undefined, { timeout: 10_000 });
  await page.waitForTimeout(500);
  return (await page.evaluate(() => window.__vitals!))!;
}