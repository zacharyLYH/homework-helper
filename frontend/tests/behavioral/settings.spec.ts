import { test, expect } from "../base.fixture";
import type { Page } from "@playwright/test";
import { EMPTY_LLM_CONFIG, stubLlmConfig } from "../helpers/stream";

// Adds a model through the dialog (provider optional, defaults to Gemini).
async function addModel(page: Page, opts: { alias: string; key: string; model?: RegExp; provider?: string }) {
  await page.getByRole("button", { name: "Add model" }).last().click();
  if (opts.provider) {
    await page.getByRole("combobox").first().click();
    await page.getByRole("option", { name: opts.provider }).click();
  }
  await page.getByRole("combobox").nth(1).click();
  await page.getByRole("option", { name: opts.model ?? /Gemini 3.7 Flash/ }).click();
  await page.getByPlaceholder("e.g. flash").fill(opts.alias);
  await page.getByPlaceholder("sk-…").fill(opts.key);
  await page.getByRole("button", { name: "Add", exact: true }).click();
}

const WIRED_CONFIG = {
  version: 1,
  name: "My Config",
  triplets: [
    { alias: "flash", provider: "gemini", model: "gemini-3.7-flash", api_key: "sk-f****cret", has_key: true },
    { alias: "deep", provider: "openrouter", model: "deepseek/deepseek-v4-flash-0731", api_key: "sk-f****cret", has_key: true },
  ],
  chat: { order: ["flash"], rules: [] },
  memory: { order: ["deep"], rules: [] },
};

// Empty config → add a model → immediate test → explicit continue through
// chat/memory wiring to the final test step.
test("guided setup flow tests each model on creation", async ({ page }) => {
  await stubLlmConfig(page, EMPTY_LLM_CONFIG);
  await page.goto("/settings");

  // Empty state: locked stepper, no continue yet
  await expect(page.getByRole("button", { name: "Add model" }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: /2 Chat/ })).toBeDisabled();

  // Add a model
  await page.getByRole("button", { name: "Add model" }).first().click();
  await page.getByRole("combobox").nth(1).click();
  await page.getByRole("option", { name: /Gemini 3.7 Flash/ }).click();
  await page.getByPlaceholder("e.g. flash").fill("flash");
  await page.getByPlaceholder("sk-…").fill("sk-test");
  await page.getByRole("button", { name: "Add", exact: true }).click();

  // Stays on Models; the model was pinged immediately and auto-saved
  await expect(page.getByText("42ms", { exact: true })).toBeVisible();
  await expect(page.getByText(/Each model is tested automatically/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Continue to Chat" })).toBeVisible();
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();

  // Explicit continue: Chat → wire → Memory → wire → Test
  await page.getByRole("button", { name: "Continue to Chat" }).click();
  await expect(page.getByRole("button", { name: "Continue to Memory" })).toBeDisabled();
  await page.getByRole("combobox").click();
  await page.getByRole("option", { name: "flash" }).click();
  await page.getByRole("button", { name: "Continue to Memory" }).click();
  await page.getByRole("combobox").click();
  await page.getByRole("option", { name: "flash" }).click();
  await page.getByRole("button", { name: "Continue to Test" }).click();

  // Final step: summary + optional test
  await expect(page.getByText("flash", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Test", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Back to chat" }).last()).toBeVisible();
});

// The API-key field coaches first-time users: why, where to get a key, cost.
test("dialog guides first-time users through the API key", async ({ page }) => {
  await stubLlmConfig(page, EMPTY_LLM_CONFIG);
  await page.goto("/settings");
  await page.getByRole("button", { name: "Add model" }).first().click();

  await expect(page.getByText(/The key lets Google Gemini run the model on your behalf/)).toBeVisible();
  await expect(page.getByRole("link", { name: /Get a key/ })).toHaveAttribute(
    "href",
    "https://aistudio.google.com/apikey",
  );

  // Provider switch updates the link + billing copy
  await page.getByRole("combobox").first().click();
  await page.getByRole("option", { name: "OpenRouter" }).click();
  await expect(page.getByRole("link", { name: /Get a key/ })).toHaveAttribute("href", "https://openrouter.ai/keys");
  await expect(page.getByText(/billed by OpenRouter/)).toBeVisible();

  // Free image-capable model is offered and flagged as free
  await page.getByRole("combobox").nth(1).click();
  await expect(page.getByRole("option", { name: /Nemotron 3 Nano Omni/ })).toBeVisible();
  await expect(page.getByRole("option", { name: /OpenRouter Free/ })).toBeVisible();
  await page.getByRole("option", { name: /Nemotron 3 Nano Omni/ }).click();
  await expect(page.getByText(/this model is free/)).toBeVisible();
});

// Without a config, chat hides the composer and points at Settings.
test("chat is gated until an LLM is configured", async ({ page }) => {
  await stubLlmConfig(page, EMPTY_LLM_CONFIG);
  await page.goto("/chat");

  await expect(page.getByText("No active LLM")).toBeVisible();
  await expect(page.getByPlaceholder("Type your message...")).not.toBeVisible();
  await page.getByRole("button", { name: "Activate your LLM" }).click();
  await expect(page).toHaveURL(/\/settings$/);
});

// Advanced (routing rules, YAML) stays collapsed until asked for.
test("advanced section hides routing rules and YAML behind an accordion", async ({ page }) => {
  await stubLlmConfig(page, WIRED_CONFIG);
  await page.goto("/settings");

  await expect(page.getByText("Chat fallbacks")).not.toBeVisible();
  await page.getByRole("button", { name: "Advanced" }).click();
  await expect(page.getByText("Chat fallbacks")).toBeVisible();
  await expect(page.getByText("Memory fallbacks")).toBeVisible();
  await expect(page.getByRole("button", { name: /Export YAML/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Import YAML/ })).toBeVisible();
});

// --- edge cases ---

// A bad key fails the immediate ping: the row is marked, the error is
// surfaced, and the flow is not blocked.
test("failed test marks the row and does not block the flow", async ({ page }) => {
  await stubLlmConfig(page, EMPTY_LLM_CONFIG);
  await page.goto("/settings");
  await addModel(page, { alias: "flash", key: "sk-bad-key" });

  await expect(page.getByText("failed", { exact: true })).toBeVisible();
  await page.getByText("failed", { exact: true }).hover();
  await expect(page.getByText("HTTP 401: invalid api key")).toBeVisible();
  // config still saved, flow still navigable
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Continue to Chat" })).toBeVisible();
});

// Duplicate aliases are rejected by save (mirrors the backend 422).
test("duplicate alias surfaces a save failure", async ({ page }) => {
  await stubLlmConfig(page, EMPTY_LLM_CONFIG);
  await page.goto("/settings");
  await addModel(page, { alias: "flash", key: "sk-test" });
  await expect(page.getByText("42ms", { exact: true })).toBeVisible();

  await addModel(page, { alias: "flash", key: "sk-test-2" });
  await expect(page.getByText("Save failed", { exact: true })).toBeVisible();
});

// Removing a wired model cleans it out of the chat/memory orders.
test("deleting a wired model clears its chat order", async ({ page }) => {
  await stubLlmConfig(page, WIRED_CONFIG);
  await page.goto("/settings");
  await expect(page.getByRole("button", { name: "Continue to Chat" })).toBeVisible();

  await page.getByRole("button", { name: "Remove" }).first().click();
  await page.getByRole("button", { name: /2 Chat/ }).click();
  await expect(page.getByText("Pick a model.")).toBeVisible();
});

// The dialog requires model + alias + key before Add enables.
test("add dialog validates before enabling Add", async ({ page }) => {
  await stubLlmConfig(page, EMPTY_LLM_CONFIG);
  await page.goto("/settings");
  await page.getByRole("button", { name: "Add model" }).first().click();

  const addBtn = page.getByRole("button", { name: "Add", exact: true });
  await expect(addBtn).toBeDisabled();
  await page.getByRole("combobox").nth(1).click();
  await page.getByRole("option", { name: /Gemini 3.7 Flash/ }).click();
  await page.getByPlaceholder("e.g. flash").fill("flash");
  await expect(addBtn).toBeDisabled(); // still missing the key
  await page.getByPlaceholder("sk-…").fill("sk-test");
  await expect(addBtn).toBeEnabled();
});

// Editing a model re-runs the ping with the new key.
test("editing a model re-tests with the new key", async ({ page }) => {
  await stubLlmConfig(page, EMPTY_LLM_CONFIG);
  await page.goto("/settings");
  await addModel(page, { alias: "flash", key: "sk-test" });
  await expect(page.getByText("42ms", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Edit" }).first().click();
  await page.getByPlaceholder("Leave blank to keep current").fill("sk-bad-key");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("failed", { exact: true })).toBeVisible();
});
