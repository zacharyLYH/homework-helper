import { test, expect } from "../base.fixture";
import { ChatPage } from "../pages/chat.page";
import { WhiteboardPage } from "../pages/whiteboard.page";
import { captureStream } from "../helpers/stream";

const textbox = (page: import("@playwright/test").Page) =>
  page.getByPlaceholder("Type your message...");

// Goes to the whiteboard via the composer's More menu, draws, and submits the
// drawing back to the chat. All assertions for the flow live here in this test.
async function drawFromWhiteboard(page: import("@playwright/test").Page) {
  const chat = new ChatPage(page);
  await chat.chooseMenuItem("Whiteboard");
  await expect(page).toHaveURL(/\/whiteboard\?chatId=10/);

  const whiteboard = new WhiteboardPage(page);
  await expect(whiteboard.attachButton()).toBeDisabled();
  await whiteboard.drawStroke();
  await expect(whiteboard.attachButton()).toBeEnabled();
  await whiteboard.attachToChat();

  await expect(page).toHaveURL(/\/chat\?chatId=10/);
  await expect(page.getByText("Whiteboard drawing.png")).toBeVisible();
}

test("sends an attached image together with a quote", async ({ page }) => {
  const chat = new ChatPage(page);
  await chat.goto();
  await chat.selectChat("Algebra review");

  await chat.attachImage("meme.png");
  await expect(page.getByText("meme.png")).toBeVisible();
  const quoted = await chat.selectAssistantText();
  await expect(page.getByRole("menu")).toContainText("Ask Homework Helper");
  await page.getByRole("menu").click();

  const stream = await captureStream(page);
  await textbox(page).fill("Explain this meme");
  await textbox(page).press("Enter");

  await expect(page.getByText("The answer is 4.")).toBeVisible();
  await expect.poll(async () => (await stream.all()).length).toBe(1);
  const [payload] = await stream.all();

  expect(payload.message).toBe("Explain this meme");
  expect(payload.quote).toBe(quoted);
  expect(String(payload.image)).toContain("iVBOR");
  expect(payload.image_media_type).toBe("image/png");

  const userBubble = page.locator('[data-message-role="user"]');
  await expect(userBubble.getByText(quoted)).toBeVisible();
  await expect(userBubble.locator('img[alt="meme.png"]')).toBeVisible();
});

test("sends a whiteboard drawing together with a quote", async ({ page }) => {
  const chat = new ChatPage(page);
  await chat.goto();
  await chat.selectChat("Algebra review");

  await drawFromWhiteboard(page);
  const quoted = await chat.selectAssistantText();
  await expect(page.getByRole("menu")).toContainText("Ask Homework Helper");
  await page.getByRole("menu").click();

  const stream = await captureStream(page);
  await textbox(page).fill("Here is my diagram");
  await textbox(page).press("Enter");

  await expect(page.getByText("The answer is 4.")).toBeVisible();
  await expect.poll(async () => (await stream.all()).length).toBe(1);
  const [payload] = await stream.all();

  expect(payload.message).toBe("Here is my diagram");
  expect(payload.quote).toBe(quoted);
  expect(String(payload.image)).toContain("iVBOR");
  expect(payload.image_media_type).toBe("image/png");
  expect(payload.is_diagram).toBe(true);

  await expect(
    page.locator('[data-message-role="user"] img[alt="Whiteboard drawing.png"]'),
  ).toBeVisible();
});

test("an attached image blocks the whiteboard until it is removed", async ({ page }) => {
  const chat = new ChatPage(page);
  await chat.goto();
  await chat.selectChat("Algebra review");
  await chat.attachImage("meme.png");
  await expect(page.getByText("meme.png")).toBeVisible();

  await chat.openMenu();
  await expect(page.getByRole("menuitem", { name: "Whiteboard" })).toBeDisabled();
  await page.keyboard.press("Escape");

  // Removing the attachment unlocks the whiteboard again.
  await page.getByRole("button", { name: "Remove attachment" }).click();
  await chat.openMenu();
  await expect(page.getByRole("menuitem", { name: "Whiteboard" })).toBeEnabled();
});

test("a whiteboard drawing blocks image attachment until it is removed", async ({ page }) => {
  const chat = new ChatPage(page);
  await chat.goto();
  await chat.selectChat("Algebra review");

  await drawFromWhiteboard(page);

  await chat.openMenu();
  await expect(page.getByRole("menuitem", { name: "Attach image" })).toBeDisabled();
  await page.keyboard.press("Escape");

  // Removing the drawing re-enables image attachment, which then works.
  await page.getByRole("button", { name: "Remove attachment" }).click();
  await chat.attachImage("photo.png");
  await expect(page.getByText("photo.png")).toBeVisible();
  await expect(page.getByText("Whiteboard drawing.png")).not.toBeVisible();
});