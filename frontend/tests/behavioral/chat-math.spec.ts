import { test, expect } from "../base.fixture";
import { ChatPage } from "../pages/chat.page";
import { captureStream } from "../helpers/stream";

test.beforeEach(async ({ page }) => {
  await new ChatPage(page).goto();
  await new ChatPage(page).selectChat("Algebra review");
});

test("inserts a math equation and renders it as KaTeX", async ({ page }) => {
  await page.locator("form").getByRole("button").first().click();
  await page.getByRole("menuitem", { name: "Insert math equation" }).click();

  await expect(page.getByText("Type a math expression")).toBeVisible();

  await page.locator("math-field").evaluate((el) => {
    (el as unknown as { value: string }).value = "x^2";
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await page.getByRole("button", { name: /Insert/ }).click();

  const textbox = page.getByPlaceholder("Type your message...");
  await expect(textbox).toHaveValue("$$x^2$$");

  const stream = await captureStream(page);
  await textbox.press("Enter");

  await expect(page.getByText("The answer is 4.")).toBeVisible();
  await expect.poll(async () => (await stream.all()).length).toBe(1);
  const [payload] = await stream.all();
  expect(payload.message).toBe("$$x^2$$");

  await expect(page.locator('[data-message-role="user"] .katex')).toBeVisible();
});