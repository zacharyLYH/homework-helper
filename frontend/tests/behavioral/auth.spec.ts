import { test, expect } from "../base.fixture";
import { ChatPage } from "../pages/chat.page";
import { LoginPage } from "../pages/login.page";

test.describe("unauthenticated", () => {
  test.use({ auth: "none" });

  test("unauthenticated users are redirected to login", async ({ page }) => {
    await page.goto("/chat");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("login flow redirects to chat", async ({ page }) => {
    const login = new LoginPage(page);
    await login.goto();
    await login.signIn();
    await expect(page).toHaveURL(/\/chat$/);
  });
});

test("authenticated users land on chat", async ({ page }) => {
  await new ChatPage(page).goto();
  await expect(page.getByText("Mathematics", { exact: true })).toBeVisible();
});
