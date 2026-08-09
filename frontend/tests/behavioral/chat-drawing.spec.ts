import { test, expect } from "../base.fixture";
import { ChatPage } from "../pages/chat.page";
import { WhiteboardPage } from "../pages/whiteboard.page";
import { captureStream, sseEvent, sseStream, stubStream } from "../helpers/stream";
import type { WhiteboardElement } from "../../src/lib/whiteboard";

const textbox = (page: import("@playwright/test").Page) =>
  page.getByPlaceholder("Type your message...");

// Goes to the whiteboard via the composer's More menu, draws, and submits the
// drawing back to the chat. All flow assertions live here in this test file.
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

test.beforeEach(async ({ page }) => {
  await new ChatPage(page).goto();
  await new ChatPage(page).selectChat("Algebra review");
});

test("shows a whiteboard drawing as a user message when submitted from the chat", async ({ page }) => {
  await drawFromWhiteboard(page);

  const stream = await captureStream(page);
  await textbox(page).fill("Here is my free-body diagram");
  await textbox(page).press("Enter");

  const userBubble = page.locator('[data-message-role="user"]').last();
  await expect(userBubble.getByText("Here is my free-body diagram")).toBeVisible();
  await expect(userBubble.locator('img[alt="Whiteboard drawing.png"]')).toBeVisible();

  await expect.poll(async () => (await stream.all()).length).toBe(1);
  const [payload] = await stream.all();
  expect(payload.message).toBe("Here is my free-body diagram");
  expect(payload.is_diagram).toBe(true);
  expect(payload.image_media_type).toBe("image/png");
  expect(String(payload.image)).toContain("iVBOR");
});

test("renders an assistant Konva drawing as an image in the assistant message", async ({ page }) => {
  const elements: WhiteboardElement[] = [
    { type: "rect", id: "box", x: 40, y: 40, w: 200, h: 80, stroke: "#22c55e", strokeWidth: 2 },
    { type: "line", id: "axis", points: [[40, 120], [240, 120]], stroke: "#94a3b8", strokeWidth: 2 },
  ];
  await stubStream(
    page,
    sseStream([
      sseEvent.drawing(elements),
      sseEvent.token("Here is the diagram."),
      sseEvent.done(),
    ]),
  );

  await textbox(page).fill("Draw a diagram");
  await textbox(page).press("Enter");

  const assistant = page.locator('[data-message-role="assistant"]').last();
  const drawing = assistant.locator('img[alt="AI diagram"]');
  await expect(drawing).toBeVisible();
  await expect(drawing).toHaveAttribute("src", /data:image\/png;base64,iVBOR/);
  await expect(assistant).toContainText("Here is the diagram.");
});