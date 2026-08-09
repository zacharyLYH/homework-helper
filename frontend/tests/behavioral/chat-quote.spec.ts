import { test, expect } from "../base.fixture";
import { ChatPage } from "../pages/chat.page";
import { captureStream } from "../helpers/stream";

const QUOTE_TEXT = "Subtract 2 from both sides, so x = 3.";

test.beforeEach(async ({ page }) => {
  await new ChatPage(page).goto();
  await new ChatPage(page).selectChat("Algebra review");
});

async function selectAssistantText(page: import("@playwright/test").Page) {
  await page
    .locator('[data-message-role="assistant"]')
    .first()
    .evaluate((el) => {
      const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      const node = walker.nextNode() as Text;
      const range = document.createRange();
      range.setStart(node, 0);
      range.setEnd(node, node.data.length);
      const sel = window.getSelection();
      sel?.removeAllRanges();
      sel?.addRange(range);
    });
  await expect(page.getByRole("menu")).toContainText("Ask Homework Helper");
}

test("quotes an assistant message and sends it", async ({ page }) => {
  await selectAssistantText(page);
  await page.getByRole("menu").click();

  const stream = await captureStream(page);
  const textbox = page.getByPlaceholder("Type your message...");
  await textbox.fill("Thanks, that helps!");
  await textbox.press("Enter");

  await expect(page.getByText("The answer is 4.")).toBeVisible();
  await expect.poll(async () => (await stream.all()).length).toBe(1);
  const [payload] = await stream.all();
  expect(payload.quote).toBe(QUOTE_TEXT);
  expect(payload.message).toBe("Thanks, that helps!");

  await expect(page.locator('[data-message-role="user"]').getByText(QUOTE_TEXT)).toBeVisible();
});

test("clears a pending quote before sending", async ({ page }) => {
  await selectAssistantText(page);
  await page.getByRole("menu").click();

  const preview = page.locator("form").getByText(QUOTE_TEXT);
  await expect(preview).toBeVisible();
  await preview.locator("xpath=..").getByRole("button").click();
  await expect(page.locator("form").getByText(QUOTE_TEXT)).toHaveCount(0);

  const stream = await captureStream(page);
  const textbox = page.getByPlaceholder("Type your message...");
  await textbox.fill("Thanks, that helps!");
  await textbox.press("Enter");

  await expect.poll(async () => (await stream.all()).length).toBe(1);
  const [payload] = await stream.all();
  expect(payload.quote).toBeUndefined();
  expect(payload.message).toBe("Thanks, that helps!");
});