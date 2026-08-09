import { test, expect } from "../base.fixture";
import { ChatPage } from "../pages/chat.page";
import { sseEvent, sseStream, stubStream } from "../helpers/stream";

test.beforeEach(async ({ page }) => {
  await new ChatPage(page).goto();
  await new ChatPage(page).selectChat("Algebra review");
});

const textbox = (page: import("@playwright/test").Page) =>
  page.getByPlaceholder("Type your message...");

async function send(page: import("@playwright/test").Page, text: string) {
  await textbox(page).fill(text);
  await textbox(page).press("Enter");
}

test("shows a searching chip while a web_search tool runs", async ({ page }) => {
  await stubStream(
    page,
    sseStream([sseEvent.toolCall("t1", "web_search", { query: "prime numbers" })]),
  );

  await send(page, "What are prime numbers?");

  await expect(page.getByText('Searching for "prime numbers"')).toBeVisible();
  await expect(textbox(page)).toBeDisabled();
});

test("renders a searched chip and answer after a web_search completes", async ({ page }) => {
  await stubStream(
    page,
    sseStream([
      sseEvent.toolCall("t1", "web_search", { query: "prime numbers" }),
      sseEvent.token("2, 3, 5 and 7 are prime."),
      sseEvent.done(),
    ]),
  );

  await send(page, "What are prime numbers?");

  await expect(page.getByText('Searched for "prime numbers"')).toBeVisible();
  await expect(page.getByText("2, 3, 5 and 7 are prime.")).toBeVisible();
});

test("renders a used chip for a non-search tool", async ({ page }) => {
  await stubStream(
    page,
    sseStream([
      sseEvent.toolCall("t2", "calculator", { expression: "22 * 3" }),
      sseEvent.token("66"),
      sseEvent.done(),
    ]),
  );

  await send(page, "What is 22 times 3?");

  await expect(page.getByText("Used calculator")).toBeVisible();
  await expect(page.getByText("66")).toBeVisible();
});