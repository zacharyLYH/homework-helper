import { test, expect } from "../base.fixture";
import { ChatPage } from "../pages/chat.page";

test("loads navigation and sidebar chats", async ({ page }) => {
  const chat = new ChatPage(page);
  await chat.goto();
  await expect(page.getByText("Mathematics", { exact: true })).toBeVisible();
  await expect(page.getByText("Algebra review", { exact: true })).toBeVisible();
});

test("shows messages for a selected chat", async ({ page }) => {
  const chat = new ChatPage(page);
  await chat.goto();
  await chat.selectChat("Algebra review");
  await expect(page.getByText("How do I solve x + 2 = 5?")).toBeVisible();
  await expect(page.getByText("Subtract 2 from both sides, so x = 3.")).toBeVisible();
});

test("creates a chat", async ({ page }) => {
  const chat = new ChatPage(page);
  await chat.goto();
  await chat.createChat("Mathematics");
  await expect(page.getByText("How do I solve x + 2 = 5?")).toBeVisible();
});
