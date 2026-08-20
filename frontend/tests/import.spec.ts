import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("import surface is keyboard reachable and has no accessibility violations", async ({ page }) => {
  await page.goto("/?e2e=1");

  await expect(page.getByRole("heading", { name: "Bring your recordings home." })).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Add evidence" })).toBeFocused();

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("Susan can stage multiple recordings without remembering their folder", async ({ page }) => {
  await page.goto("/?e2e=1");

  await page.getByRole("button", { name: "Choose files" }).click();
  await expect(page.getByRole("heading", { name: "2 files selected" })).toBeVisible();
  await page.getByRole("button", { name: "Use this selection" }).click();

  await expect(page.getByRole("status")).toContainText("has not saved a folder permission");
  await expect(page.getByText("Remembered locations").locator("..")).toContainText("0");
});

test("remembered recording folder keeps discovery separate from processing", async ({ page }) => {
  await page.goto("/?e2e=1");

  await page.getByRole("button", { name: "Choose folder" }).click();
  await page.getByRole("radio", { name: /Remember this folder/ }).check();
  await page.getByText("Advanced processing policy").click();
  await page.getByRole("checkbox", { name: /Automatically process newly discovered recordings/ }).check();
  await page.getByRole("button", { name: "Remember this folder" }).click();

  await expect(page.getByRole("status")).toContainText("2 recordings discovered");
  await expect(page.getByRole("status")).toContainText("nothing was transcribed automatically");
});

test("transcript libraries never offer automatic processing", async ({ page }) => {
  await page.goto("/?e2e=1");

  await page.getByRole("tab", { name: "Existing transcripts" }).click();
  await page.getByRole("button", { name: "Choose folder" }).click();
  await page.getByRole("radio", { name: /Remember this folder/ }).check();

  await expect(page.getByText("Advanced processing policy")).toHaveCount(0);
  await page.getByRole("button", { name: "Remember this folder" }).click();
  await expect(page.getByRole("status")).toContainText("reconciled with EchoFlow's local index");
});

test("theme switching uses the compact picker and preserves semantics", async ({ page }) => {
  await page.goto("/?e2e=1");

  await page.getByLabel("Theme").selectOption("midnight");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "midnight");
  await expect(page.getByRole("heading", { name: "Add local evidence without giving up custody." })).toBeVisible();

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
