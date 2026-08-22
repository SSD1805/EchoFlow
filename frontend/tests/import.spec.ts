import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("import surface is keyboard reachable and has no accessibility violations", async ({ page }) => {
  await page.goto("/?e2e=1");

  await expect(page.getByRole("heading", { name: "Add local recordings and transcripts." })).toBeVisible();
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

  await expect(page.getByRole("status")).toContainText("folder was not saved");
  await expect(page.getByText("Remembered folders").locator("..")).toContainText("0");
});

test("remembered recording folder makes discovery explicit and separate from transcription", async ({ page }) => {
  await page.goto("/?e2e=1");

  await page.getByRole("button", { name: "Choose folder" }).click();
  await page.getByRole("radio", { name: /Remember this folder/ }).check();
  await page.getByText("Automatic transcription").click();
  await page.getByRole("checkbox", { name: /Automatically transcribe new recordings found here/ }).check();
  await page.getByRole("button", { name: "Remember this folder" }).click();

  await expect(page.getByRole("status")).toContainText("Scholion found 2 recordings");
  await expect(page.getByRole("status")).toContainText("did not start transcription");

  await page.getByRole("button", { name: "Check remembered folders" }).click();
  await expect(page.getByRole("status")).toContainText("Checked remembered recording folders");
  await expect(page.getByRole("status")).toContainText("No transcription was started");
});

test("transcript folders never offer automatic transcription", async ({ page }) => {
  await page.goto("/?e2e=1");

  await page.getByRole("tab", { name: "Existing transcripts" }).click();
  await page.getByRole("button", { name: "Choose folder" }).click();
  await page.getByRole("radio", { name: /Remember this folder/ }).check();

  await expect(page.getByText("Automatic transcription")).toHaveCount(0);
  await page.getByRole("button", { name: "Remember this folder" }).click();
  await expect(page.getByRole("status")).toContainText("checked it for transcript files and updated Library search");
});

test("theme switching uses the compact picker and preserves semantics", async ({ page }) => {
  await page.goto("/?e2e=1");

  await page.getByLabel("Theme").selectOption("midnight");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "midnight");
  await expect(page.getByRole("heading", { name: "Choose files once, or remember a folder." })).toBeVisible();

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
