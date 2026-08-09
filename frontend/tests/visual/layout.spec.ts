import { test, expect } from "../base.fixture";
import { maskDynamicContent } from "./masking";

const viewports = [
  { width: 375, height: 667 },
  { width: 768, height: 1024 },
  { width: 1280, height: 720 },
];

for (const viewport of viewports) {
  test.describe(`${viewport.width}x${viewport.height}`, () => {
    test.use({ viewport });
    const tag = `${viewport.width}x${viewport.height}`;

    test("chat layout", async ({ page }) => {
      await page.goto("/chat");
      await expect(page).toHaveScreenshot(`chat-${tag}.png`, {
        animations: "disabled",
        mask: [maskDynamicContent(page)],
      });
    });

    test("whiteboard layout", async ({ page }) => {
      await page.goto("/whiteboard?chatId=10");
      await expect(page).toHaveScreenshot(`whiteboard-${tag}.png`, {
        animations: "disabled",
        mask: [maskDynamicContent(page)],
      });
    });

    test.describe("login (unauthenticated)", () => {
      test.use({ auth: "none" });

      test("login layout", async ({ page }) => {
        await page.goto("/login");
        await expect(page).toHaveScreenshot(`login-${tag}.png`, {
          animations: "disabled",
          mask: [maskDynamicContent(page)],
        });
      });
    });
  });
}