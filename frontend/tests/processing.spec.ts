import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

async function openProcessing(
  page: import("@playwright/test").Page,
  querySuffix = "",
) {
  await page.goto(`/?e2e=1${querySuffix}`);
  await page.getByRole("button", { name: "Processing" }).click();
  await expect(
    page.getByRole("heading", { name: "Transcribe recordings." }),
  ).toBeVisible();
  await expect(page.getByText("NVIDIA GeForce RTX 4080")).toBeVisible();
}

test("Processing Center presents the hardware used for local planning and stays accessible", async ({ page }) => {
  await openProcessing(page);

  await expect(page.getByRole("heading", { name: "Ready", exact: true })).toBeVisible();
  await expect(page.getByText("AMD Ryzen 7 7700X 8-Core Processor")).toBeVisible();
  await expect(page.getByText("16 threads available")).toBeVisible();
  await expect(page.getByText("52 GB available")).toBeVisible();
  await expect(page.getByText("64 GB installed")).toBeVisible();
  await expect(page.getByText("14 GB graphics memory available")).toBeVisible();
  await expect(page.getByText(/does not send hardware information or telemetry anywhere/)).toBeVisible();

  await page.getByText("How Scholion chose these limits").click();
  await expect(page.getByText("FFmpeg and FFprobe are available")).toBeVisible();
  await expect(page.getByText("DuckDB")).toHaveCount(0);
  await expect(page.getByText("SQLite")).toHaveCount(0);

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
});

test("Susan can choose a recording and review its transcription setup before start", async ({ page }) => {
  await openProcessing(page);

  await page.getByRole("button", { name: "Choose recording" }).click();
  await expect(page.getByRole("status")).toContainText("interview-01.m4a selected");
  await page.getByRole("button", { name: "Check recording" }).click();

  const preflight = page.getByLabel("Transcription setup");
  await expect(preflight).toBeVisible();
  await expect(page.getByRole("status")).toContainText("Ready to transcribe interview-01.m4a");
  await expect(page.getByRole("button", { name: "Start transcription" })).toBeEnabled();
  await expect(page.getByRole("group", { name: "Choose the audio track to transcribe" })).toHaveCount(0);
});

test("multiple embedded audio tracks require an explicit backend-bound choice", async ({ page }) => {
  await openProcessing(page, "&multitrack=1");

  await page.getByRole("button", { name: "Choose recording" }).click();
  await page.getByRole("button", { name: "Check recording" }).click();

  const chooser = page.getByRole("group", { name: "Choose the audio track to transcribe" });
  await expect(chooser).toBeVisible();
  await expect(chooser).toContainText("Camera scratch");
  await expect(chooser).toContainText("Lav microphone");
  await expect(chooser).toContainText("eng");
  await expect(chooser).toContainText("container default");
  await expect(chooser.getByRole("radio")).toHaveCount(2);
  await expect(chooser.getByRole("radio").first()).not.toBeChecked();
  await expect(chooser.getByRole("radio").last()).not.toBeChecked();

  const start = page.getByRole("button", { name: "Start transcription" });
  await expect(start).toBeDisabled();

  await chooser.getByRole("radio", { name: /Lav microphone/ }).check();
  await expect(page.getByRole("status")).toContainText("Audio track #3 selected");
  await expect(chooser.getByRole("radio", { name: /Lav microphone/ })).toBeChecked();
  await expect(start).toBeEnabled();

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
});

test("starting work uses the local-task path", async ({ page }) => {
  await openProcessing(page);
  await page.getByRole("button", { name: "Choose recording" }).click();
  await page.getByRole("button", { name: "Check recording" }).click();
  await page.getByRole("button", { name: "Start transcription" }).click();

  await expect(page.getByRole("status").filter({ hasText: "Transcription started on this computer" })).toBeVisible();
  await expect(page.getByText(/Transcribing interview-01\.m4a/)).toBeVisible();
});

test("interrupted work offers resume and a fresh retry as distinct actions", async ({ page }) => {
  await openProcessing(page);

  await expect(page.getByText("oral-history-07.m4a", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Resume", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry from beginning" }).first()).toBeVisible();

  await page.getByRole("button", { name: "Retry from beginning" }).first().click();
  await expect(page.getByRole("status")).toContainText("A fresh retry is ready for oral-history-07.m4a");
  await expect(page.getByRole("status")).toContainText("earlier job has not been changed");
});
