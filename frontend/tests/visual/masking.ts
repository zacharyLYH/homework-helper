import type { Page } from "@playwright/test";

export function maskDynamicContent(page: Page) {
  return page.locator("time, [data-testid='timestamp'], [data-testid='dynamic-id']");
}
