import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("plain Vite explains how to choose a development mode instead of impersonating Tauri", async ({ page }) => {
  await page.goto("http://127.0.0.1:4173/");

  await expect(
    page.getByRole("heading", { name: "You opened the Vite server without a desktop host." }),
  ).toBeVisible();
  await expect(page.getByText("npm run dev:mock", { exact: true })).toBeVisible();
  await expect(page.getByText("npm run tauri dev", { exact: true })).toBeVisible();
  await expect(page.getByText("npm run doctor:desktop", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Add evidence" })).toHaveCount(0);

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("explicit mock mode still renders the interactive EchoFlow workspace", async ({ page }) => {
  await page.goto("/?e2e=1");

  await expect(page.getByRole("button", { name: "Add evidence" })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "You opened the Vite server without a desktop host." }),
  ).toHaveCount(0);
});
