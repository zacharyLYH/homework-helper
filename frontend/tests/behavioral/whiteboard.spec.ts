import { test, expect } from "../base.fixture";
import { WhiteboardPage } from "../pages/whiteboard.page";

test("loads the whiteboard toolbar", async ({ page }) => {
  const whiteboard = new WhiteboardPage(page);
  await whiteboard.goto();
  await expect(whiteboard.tool(0)).toBeVisible();
  await expect(whiteboard.tool(1)).toHaveAttribute("aria-pressed", "true");
});

test("changes the active tool", async ({ page }) => {
  const whiteboard = new WhiteboardPage(page);
  await whiteboard.goto();
  await whiteboard.tool(0).click();
  await expect(whiteboard.tool(0)).toHaveAttribute("aria-pressed", "true");
  await expect(whiteboard.tool(1)).toHaveAttribute("aria-pressed", "false");
});

test("switches through every drawing tool", async ({ page }) => {
  const whiteboard = new WhiteboardPage(page);
  await whiteboard.goto();

  const tools = whiteboard.tools();
  await expect(tools).toHaveCount(8);

  for (let i = 0; i < 8; i++) {
    await tools.nth(i).click();
    await expect(tools.nth(i)).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator('button[aria-pressed="true"]')).toHaveCount(1);
  }
});

test("drawing with each main tool enables attach to chat", async ({ page }) => {
  const whiteboard = new WhiteboardPage(page);
  await whiteboard.goto();

  const attach = page.getByRole("button", { name: "Attach to chat" });
  await expect(attach).toBeDisabled();

  const canvas = page.locator("canvas").first();
  const box = await canvas.boundingBox();
  if (!box) throw new Error("canvas has no bounding box");
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;

  for (const i of [1, 2, 3, 4, 5]) {
    await whiteboard.tool(i).click();
    await page.mouse.move(cx - 80, cy);
    await page.mouse.down();
    await page.mouse.move(cx + 80, cy);
    await page.mouse.up();
    await expect(attach).toBeEnabled();
  }

  await page.locator('button[title="Clear canvas"]').click();
  await expect(attach).toBeDisabled();
});
