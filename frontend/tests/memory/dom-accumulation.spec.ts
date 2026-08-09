import { test } from "../base.fixture";

test("reports DOM and heap changes after reload", async ({ page, context }) => {
  await page.goto("/chat");
  const before = await page.locator("*").count();
  await page.reload();
  const after = await page.locator("*").count();
  const memory = await page.evaluate(() => {
    const value = (performance as Performance & { memory?: { usedJSHeapSize: number } }).memory?.usedJSHeapSize;
    return value ?? 0;
  });
  let heap = 0;
  try {
    const client = await context.newCDPSession(page);
    heap = (await client.send("Runtime.getHeapUsage")).usedSize;
  } catch {
    // CDP is unavailable outside Chromium; the DOM count remains useful.
  }
  console.log(`DOM nodes: ${before} -> ${after} (diff ${after - before})`);
  console.log(`Heap: ${memory || heap} bytes`);
});
