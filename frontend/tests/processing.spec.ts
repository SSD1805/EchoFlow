import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

async function openProcessing(page: import("@playwright/test").Page) {
  await page.goto("/?e2e=1");
  await page.getByRole("button", { name: "Processing" }).click();
  await expect(
    page.getByRole("heading", { name: "Turn recordings into durable evidence." }),
  ).toBeVisible();
  await expect(page.getByText("Private workspace is ready")).toBeVisible();
}

test("Processing Center presents backend readiness and stays accessible", async ({ page }) => {
  await openProcessing(page);

  await expect(page.getByText("healthy", { exact: true })).toBeVisible();
  await expect(page.getByText("8 threads visible")).toBeVisible();
  await expect(page.getByText("FFmpeg and FFprobe are available")).toBeVisible();
  await expect(page.getByText("DuckDB")).toHaveCount(0);
  await expect(page.getByText("SQLite")).toHaveCount(0);

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
});

test("Susan can choose a recording and obtain a backend preflight before start", async ({ page }) => {
  await openProcessing(page);

  await page.getByRole("button", { name: "Choose recording" }).click();
  await expect(page.getByRole("status")).toContainText("interview-01.m4a selected");
  await page.getByRole("button", { name: "Run preflight" }).click();

  const preflight = page.getByLabel("Backend transcription preflight");
  await expect(preflight).toBeVisible();
  await expect(page.getByRole("status")).toContainText("Preflight complete");
  await expect(page.getByRole("button", { name: "Start local transcription" })).toBeEnabled();
});

test("starting work uses the supervised local-task path", async ({ page }) => {
  await openProcessing(page);
  await page.getByRole("button", { name: "Choose recording" }).click();
  await page.getByRole("button", { name: "Run preflight" }).click();
  await page.getByRole("button", { name: "Start local transcription" }).click();

  const launchStatus = page
    .getByRole("status")
    .filter({ hasText: "Transcription launched as a supervised local process" });
  await expect(launchStatus).toBeVisible();
  await expect(page.getByText(/Transcribing interview-01\.m4a/)).toBeVisible();
});

test("interrupted work offers resume and a fresh retry as distinct actions", async ({ page }) => {
  await openProcessing(page);

  await expect(page.getByText("oral-history-07.m4a", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Resume checkpoint" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Plan fresh retry" }).first()).toBeVisible();

  await page.getByRole("button", { name: "Plan fresh retry" }).first().click();
  await expect(page.getByRole("status")).toContainText("Fresh retry preflight complete");
  await expect(page.getByRole("status")).toContainText("interrupted job was not changed");
});
