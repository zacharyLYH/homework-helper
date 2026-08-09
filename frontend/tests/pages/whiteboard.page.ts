import { type Locator, type Page } from "@playwright/test";

// UI actions on the whiteboard page. Page objects only perform actions; tests
// keep the assertions.
export class WhiteboardPage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto("/whiteboard?chatId=10");
  }

  tools(): Locator {
    return this.page.locator("button[aria-pressed]");
  }

  tool(index: number): Locator {
    return this.tools().nth(index);
  }

  async drawStroke() {
    const canvas = this.page.locator("canvas").first();
    const box = await canvas.boundingBox();
    if (!box) throw new Error("canvas has no bounding box");
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    await this.page.mouse.move(cx - 120, cy);
    await this.page.mouse.down();
    for (let i = 1; i <= 8; i++) {
      await this.page.mouse.move(cx - 120 + i * 30, cy + Math.sin(i) * 60);
    }
    await this.page.mouse.up();
  }

  attachButton(): Locator {
    return this.page.getByRole("button", { name: "Attach to chat" });
  }

  async attachToChat() {
    await this.attachButton().click();
  }
}