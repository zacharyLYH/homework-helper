import { test, expect } from "../base.fixture";
import { ChatPage } from "../pages/chat.page";
import { captureStream } from "../helpers/stream";

const chat = (page: import("@playwright/test").Page) => new ChatPage(page);

test.beforeEach(async ({ page }) => {
  await new ChatPage(page).goto();
  await new ChatPage(page).selectChat("Algebra review");
});

const textbox = (page: import("@playwright/test").Page) =>
  page.getByPlaceholder("Type your message...");

test("attaches an image, previews it, and removes it", async ({ page }) => {
  await chat(page).attachImage("meme.png");
  await expect(page.getByText("meme.png")).toBeVisible();

  await page.getByRole("button", { name: "Remove attachment" }).click();
  await expect(page.getByText("meme.png")).not.toBeVisible();

  const stream = await captureStream(page);
  await textbox(page).fill("Please review this");
  await textbox(page).press("Enter");

  await expect.poll(async () => (await stream.all()).length).toBe(1);
  const [payload] = await stream.all();
  expect(payload.image).toBeUndefined();
});

test("sends an attached image with the message", async ({ page }) => {
  await chat(page).attachImage("diagram.png");
  await expect(page.getByText("diagram.png")).toBeVisible();

  const stream = await captureStream(page);
  await textbox(page).fill("Explain this diagram");
  await textbox(page).press("Enter");

  await expect(page.getByText("The answer is 4.")).toBeVisible();
  await expect.poll(async () => (await stream.all()).length).toBe(1);

  const [payload] = await stream.all();
  expect(payload.message).toBe("Explain this diagram");
  expect(String(payload.image)).toContain("iVBOR");
  expect(payload.image_media_type).toBe("image/png");
  expect(payload.is_diagram).toBe(false);

  await expect(page.locator('[data-message-role="user"] img[alt="diagram.png"]')).toBeVisible();
});