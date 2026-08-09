import type { Page } from "@playwright/test";

export class LoginPage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto("/login");
  }

  async signIn(email = "test@example.com", code = "123456") {
    await this.page.getByLabel("Email").fill(email);
    await this.page.getByRole("button", { name: "Send code" }).click();
    await this.page.locator("input").last().fill(code);
    await this.page.getByRole("button", { name: "Sign in" }).click();
  }
}
