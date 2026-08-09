import type { Locator, Page } from "@playwright/test";

// In-memory stand-in for a PNG the user picks from the OS file dialog.
const TINY_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

// UI actions on the chat page. Page objects only perform actions; tests keep
// the assertions.
export class ChatPage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto("/chat");
  }

  async selectChat(title: string) {
    await this.page.getByText(title, { exact: true }).click();
  }

  async createChat(subject: string) {
    await this.page.getByRole("button", { name: "New Chat" }).click();
    await this.page.getByRole("tab", { name: "New Chat" }).click();
    await this.page.getByRole("combobox", { name: "Subject" }).click();
    await this.page.getByRole("option", { name: subject }).click();
    await this.page.getByRole("button", { name: "Done" }).click();
  }

  // The composer's menu icon button: the icon button immediately before the
  // textarea (avoids matching an attachment's "Remove" button in the preview).
  moreButton(): Locator {
    return this.page
      .locator("form textarea")
      .locator("xpath=preceding-sibling::button[1]");
  }

  async openMenu() {
    await this.moreButton().click();
  }

  // Opens the More menu and picks a menu item ("Attach image"/"Whiteboard").
  async chooseMenuItem(item: string) {
    await this.openMenu();
    await this.page.getByRole("menuitem", { name: item }).click();
  }

  // Attaches an image the way a user does: More menu → "Attach image", which
  // triggers the OS file chooser.
  async attachImage(name: string) {
    await this.openMenu();
    const [chooser] = await Promise.all([
      this.page.waitForEvent("filechooser"),
      this.page.getByRole("menuitem", { name: "Attach image" }).click(),
    ]);
    await chooser.setFiles({ name, mimeType: "image/png", buffer: TINY_PNG });
  }

  // Selects the first assistant message text the way a user would. Returns the
  // text so the caller can assert it reached the wire.
  async selectAssistantText(): Promise<string> {
    return this.page
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
        return node.data;
      });
  }
}