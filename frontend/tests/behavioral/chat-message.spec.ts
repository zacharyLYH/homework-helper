import { test, expect } from "../base.fixture";
import { ChatPage } from "../pages/chat.page";
import { sseEvent, sseStream, stubStream, captureStream } from "../helpers/stream";

test.beforeEach(async ({ page }) => {
  await new ChatPage(page).goto();
  await new ChatPage(page).selectChat("Algebra review");
});

const textbox = (page: import("@playwright/test").Page) =>
  page.getByPlaceholder("Type your message...");

test("sends a message and streams a reply", async ({ page }) => {
  await textbox(page).fill("What is 2 + 2?");
  await textbox(page).press("Enter");

  await expect(page.getByText("The answer is 4.")).toBeVisible();
  await expect(textbox(page)).toHaveValue("");
});

test("shows a typing indicator while the reply streams", async ({ page }) => {
  await stubStream(
    page,
    sseStream([{ event: sseEvent.token("The answer is 4."), delay: 800 }, sseEvent.done()]),
  );

  await textbox(page).fill("What is 2 + 2?");
  await textbox(page).press("Enter");

  await expect(page.locator('[aria-busy="true"] .animate-bounce')).toHaveCount(3);
  await expect(page.getByText("The answer is 4.")).toBeVisible();
});

test("renders content progressively as tokens arrive", async ({ page }) => {
  await stubStream(
    page,
    sseStream([
      { event: sseEvent.token("The answer"), delay: 400 },
      { event: sseEvent.token(" is 4."), delay: 1500 },
      sseEvent.done(),
    ]),
  );

  await textbox(page).fill("What is 2 + 2?");
  await textbox(page).press("Enter");

  const bubble = page.locator('[data-message-role="assistant"]').last().locator("p").first();
  await expect(bubble).toHaveText("The answer");
  await expect(bubble).not.toHaveText("The answer is 4.");
  await expect(bubble).toHaveText("The answer is 4.");
});

test("renders an error bubble when the stream fails", async ({ page }) => {
  await stubStream(page, sseStream([sseEvent.error("Upstream timeout")]));

  await textbox(page).fill("What is 2 + 2?");
  await textbox(page).press("Enter");

  await expect(page.getByText("Error: Upstream timeout")).toBeVisible();
});

test("handles an empty reply gracefully", async ({ page }) => {
  await stubStream(page, sseStream([sseEvent.done()]));

  await textbox(page).fill("What is 2 + 2?");
  await textbox(page).press("Enter");

  await expect(page.locator('[data-message-role="assistant"]')).toHaveCount(2);
  await expect(page.getByText("Error:")).not.toBeVisible();
});

test("includes prior turns in the follow-up request", async ({ page }) => {
  const stream = await captureStream(page);

  await textbox(page).fill("What is 2 + 2?");
  await textbox(page).press("Enter");
  await expect(page.getByText("The answer is 4.")).toBeVisible();

  await expect(textbox(page)).toBeEnabled();
  await textbox(page).fill("And 2 * 3?");
  await textbox(page).press("Enter");
  await expect(page.getByText("The answer is 4.").last()).toBeVisible();

  await expect.poll(async () => (await stream.all()).length).toBe(2);
  const [first, second] = await stream.all();

  expect(first.chat_id).toBe(10);
  expect(first.messages).toEqual([
    { role: "user", content: "How do I solve x + 2 = 5?" },
    { role: "assistant", content: "Subtract 2 from both sides, so x = 3." },
    { role: "user", content: "What is 2 + 2?" },
  ]);

  expect(second.messages).toEqual([
    { role: "user", content: "How do I solve x + 2 = 5?" },
    { role: "assistant", content: "Subtract 2 from both sides, so x = 3." },
    { role: "user", content: "What is 2 + 2?" },
    { role: "assistant", content: "The answer is 4." },
    { role: "user", content: "And 2 * 3?" },
  ]);
});

test("copies a message to the clipboard", async ({ page }) => {
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"], {
    origin: "http://localhost:4173",
  });

  await page
    .locator('[data-message-role="assistant"]')
    .first()
    .getByRole("button")
    .first()
    .click();

  await expect
    .poll(() => page.evaluate(() => navigator.clipboard.readText()))
    .toBe("Subtract 2 from both sides, so x = 3.");
});

test("retries the last user message", async ({ page }) => {
  const stream = await captureStream(page);

  await textbox(page).fill("What is 2 + 2?");
  await textbox(page).press("Enter");
  await expect(page.getByText("The answer is 4.")).toBeVisible();

  const lastAssistant = page.locator('[data-message-role="assistant"]').last();
  await expect(lastAssistant.getByRole("button")).toHaveCount(2);
  await lastAssistant.getByRole("button").nth(1).click();

  await expect.poll(async () => (await stream.all()).length).toBe(2);
  const [, retry] = await stream.all();

  expect(retry.message).toBe("What is 2 + 2?");
  expect(retry.messages).toEqual([
    { role: "user", content: "How do I solve x + 2 = 5?" },
    { role: "assistant", content: "Subtract 2 from both sides, so x = 3." },
    { role: "user", content: "What is 2 + 2?" },
  ]);
  await expect(page.locator('[data-message-role="user"]')).toHaveCount(2);
});