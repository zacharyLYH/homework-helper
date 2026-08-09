import type { Page } from "@playwright/test";

export const GOOD = { lcpMs: 1000, fcpMs: 1000, cls: 0.1, inpMs: 200 } as const;

export const MEMORY = { heapMb: 64, domCount: 500 } as const;

export interface Vitals {
  lcp: number;
  cls: number;
  inp: number;
  fcp: number;
  events: number[];
}

export interface Memory {
  heapBytes: number;
  domCount: number;
}

declare global {
  interface Window {
    __vitals?: Vitals;
  }
}

export async function installVitals(page: Page) {
  await page.addInitScript(() => {
    const events: number[] = [];
    const v: Vitals = { lcp: 0, cls: 0, inp: 0, fcp: 0, events };
    window.__vitals = v;

    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) {
        if (e.entryType === "largest-contentful-paint") v.lcp = e.startTime;
      }
    }).observe({ type: "largest-contentful-paint", buffered: true });

    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) {
        if (e.entryType === "paint" && e.name === "first-contentful-paint") v.fcp = e.startTime;
      }
    }).observe({ type: "paint", buffered: true });

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
        if (e.entryType === "event" && e.duration >= 16) {
          v.events.push(e.duration);
          v.inp = Math.max(v.inp, e.duration);
        }
      }
    }).observe(({ type: "event", buffered: true, durationThreshold: 16 } as unknown) as PerformanceObserverInit);
  });
}

export async function readVitals(page: Page): Promise<Vitals> {
  return page.evaluate(() => window.__vitals ?? { lcp: 0, cls: 0, inp: 0, fcp: 0, events: [] });
}

export async function measureTransition(page: Page, path: string): Promise<Vitals> {
  await installVitals(page);
  await page.goto(path);
  await page.waitForLoadState("load");
  await page.waitForFunction(() => (window.__vitals?.lcp ?? 0) > 0, undefined, { timeout: 10_000 });
  await page.waitForTimeout(500);
  return (await page.evaluate(() => window.__vitals!))!;
}

export async function readMemory(page: Page): Promise<Memory> {
  return page.evaluate(() => {
    const perf = performance as Performance & { memory?: { usedJSHeapSize?: number } };
    return {
      heapBytes: perf.memory?.usedJSHeapSize ?? 0,
      domCount: document.querySelectorAll("*").length,
    };
  });
}

export async function beginInteractionPhase(page: Page): Promise<number> {
  return page.evaluate(() => {
    const v = window.__vitals;
    const baselineCls = v?.cls ?? 0;
    if (v) v.events.length = 0;
    return baselineCls;
  });
}

export async function endInteractionPhase(page: Page, baselineCls: number) {
  return page.evaluate((base) => {
    const v = window.__vitals!;
    const inp = v.events.reduce((max, d) => Math.max(max, d), 0);
    return { inp, clsDelta: v.cls - base };
  }, baselineCls);
}