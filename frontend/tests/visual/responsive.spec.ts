import { test, expect } from "../base.fixture";
import { ChatPage } from "../pages/chat.page";
import { WhiteboardPage } from "../pages/whiteboard.page";
import { maskDynamicContent } from "./masking";

type PageLike = import("@playwright/test").Page;

// One snapshot per scene, per breakpoint, per theme. Baselines are generated on
// macOS; `maxDiffPixelRatio` (global, in playwright.config) absorbs cross-OS
// font noise and `snapshotPathTemplate` drops the browser/platform suffix so
// the same baselines are used on any OS. These shots exist to verify
// responsive design, not pixel fidelity.
const VIEWPORTS = [
  { name: "phone", width: 375, height: 667 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "desktop", width: 1280, height: 720 },
] as const;

const THEMES = ["light", "dark"] as const;

type Viewport = (typeof VIEWPORTS)[number];

// Opens /chat and selects the chat the way a real user would: on phone the
// chat list is hidden behind a sidebar drawer, so open it, pick the chat, then
// close the drawer again so the shot shows the conversation.
async function openChat(page: PageLike, viewport: Viewport, title: string) {
  const chat = new ChatPage(page);
  await chat.goto();
  if (viewport.name !== "phone") {
    await chat.selectChat(title);
    return;
  }
  await page.getByRole("button", { name: "Toggle sidebar" }).click();
  await page.getByText(title, { exact: true }).waitFor();
  await chat.selectChat(title);
  await page.keyboard.press("Escape");
}

// Builds up a conversation by sending a couple of real messages through the
// composer, giving the scene a thread of a few turns.
async function buildThread(page: PageLike, viewport: Viewport, title: string) {
  await openChat(page, viewport, title);
  const chat = new ChatPage(page);
  const textbox = page.getByPlaceholder("Type your message...");
  for (const question of ["Why is 2x = 4?", "And what about fractions?"]) {
    await textbox.fill(question);
    await textbox.press("Enter");
    await expect(page.locator('[data-message-role="assistant"]').last()).toContainText(
      "The answer is 4.",
    );
    await expect(textbox).toBeEnabled();
  }
}

interface Scene {
  name: string;
  auth?: "authenticated" | "none";
  prepare(page: PageLike, viewport: Viewport): Promise<void>;
}

const SCENES: Scene[] = [
  {
    name: "login",
    auth: "none",
    prepare: async (page) => {
      await page.goto("/login");
      await page.getByPlaceholder("you@example.com").waitFor();
    },
  },
  {
    name: "chat-welcome",
    prepare: async (page) => {
      await page.goto("/chat");
      await page.getByText("Select an existing chat or create a new chat!").waitFor();
    },
  },
  {
    name: "chat-thread",
    prepare: async (page, viewport) => {
      await buildThread(page, viewport, "Algebra review");
    },
  },
  {
    name: "chat-quote",
    prepare: async (page, viewport) => {
      await openChat(page, viewport, "Algebra review");
      const chat = new ChatPage(page);
      await chat.selectAssistantText();
      await page.getByRole("menu").click();
      await page.locator("form").getByText(/Subtract 2 from both sides/).waitFor();
    },
  },
  {
    name: "chat-attachment",
    prepare: async (page, viewport) => {
      await openChat(page, viewport, "Algebra review");
      const chat = new ChatPage(page);
      await chat.attachImage("photo.png");
      await page.getByText("photo.png").waitFor();
    },
  },
  {
    name: "math-equation",
    prepare: async (page, viewport) => {
      await openChat(page, viewport, "Algebra review");
      const chat = new ChatPage(page);
      await chat.openMenu();
      await page.getByRole("menuitem", { name: "Insert math equation" }).click();
      await page.getByText("Type a math expression").waitFor();
      await page.locator("math-field").evaluate((el) => {
        (el as unknown as { value: string }).value = "\\frac{1}{2}x^2+\\sqrt{x}";
        el.dispatchEvent(new Event("input", { bubbles: true }));
      });
      await expect(page.getByRole("button", { name: /Insert/ })).toBeEnabled();
    },
  },
  {
    name: "chat-menu",
    prepare: async (page, viewport) => {
      await openChat(page, viewport, "Algebra review");
      const chat = new ChatPage(page);
      await chat.openMenu();
      await page.getByRole("menuitem", { name: "Attach image" }).waitFor();
    },
  },
  {
    name: "chat-sidebar",
    prepare: async (page, viewport) => {
      await new ChatPage(page).goto();
      if (viewport.name === "phone") {
        // Sidebar is closed behind a drawer by default on phone: open it.
        await page.getByRole("button", { name: "Toggle sidebar" }).click();
      }
      await page.getByText("Algebra review", { exact: true }).waitFor();
    },
  },
  {
    name: "new-chat",
    prepare: async (page, viewport) => {
      await new ChatPage(page).goto();
      if (viewport.name === "phone") {
        // The "New Chat" button lives in the sidebar, which on phone is the
        // hidden drawer; open it first.
        await page.getByRole("button", { name: "Toggle sidebar" }).click();
        await page.getByText("Algebra review", { exact: true }).waitFor();
      }
      await page.getByRole("button", { name: "New Chat" }).click();
      await page.getByRole("dialog").waitFor();
    },
  },
  {
    name: "whiteboard",
    prepare: async (page) => {
      await page.goto("/whiteboard?chatId=10");
      const whiteboard = new WhiteboardPage(page);
      await page.locator("canvas").waitFor();
      await whiteboard.drawStroke();
      await expect(whiteboard.attachButton()).toBeEnabled();
    },
  },
];

for (const theme of THEMES) {
  test.describe(`theme: ${theme}`, () => {
    test.use({ theme });
    for (const scene of SCENES) {
      test.describe(scene.name, () => {
        if (scene.auth) test.use({ auth: scene.auth });
        for (const viewport of VIEWPORTS) {
          test(`${scene.name} @ ${viewport.name}`, async ({ page }) => {
            await page.setViewportSize({ width: viewport.width, height: viewport.height });
            await scene.prepare(page, viewport);
            await expect(page).toHaveScreenshot(
              `${theme}-${scene.name}-${viewport.name}.png`,
              { mask: [maskDynamicContent(page)] },
            );
          });
        }
      });
    }
  });
}