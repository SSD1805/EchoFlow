import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

async function openTranscriptTools(page: import("@playwright/test").Page) {
  await page.goto("/?e2e=1");
  await page.getByRole("button", { name: "Library" }).click();
  await page.getByRole("searchbox", { name: "Search EchoFlow" }).fill("ABC");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.getByRole("button", { name: "Open transcript tools for interview-42" }).click();
  const panel = page.getByRole("complementary", { name: "Transcript tools" });
  await expect(panel.getByRole("heading", { name: "interview-42" })).toBeVisible();
  return panel;
}

test("transcript tools expose verified details without filesystem paths", async ({ page }) => {
  const panel = await openTranscriptTools(page);

  await expect(panel.getByText("24:20")).toBeVisible();
  await expect(panel.getByText("128", { exact: true })).toBeVisible();
  await expect(panel.getByText("Available locally")).toBeVisible();
  await expect(panel.getByText("aaaaaaaaaaaa…")).toBeVisible();
  await expect(panel.getByText(/\/Users\//)).toHaveCount(0);
  await expect(panel.getByText("canonical_path")).toHaveCount(0);
  await expect(panel.getByText("source_path")).toHaveCount(0);

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
});

test("speaker labels change presentation without replacing anonymous evidence refs", async ({ page }) => {
  const panel = await openTranscriptTools(page);
  const form = panel.getByRole("form", { name: "Speaker speaker-2" });
  const input = form.getByRole("textbox", { name: "Display name for speaker-2" });

  await input.fill("Dr. Chen");
  await form.getByRole("button", { name: "Save name" }).click();
  await expect(panel.getByRole("status")).toContainText("speaker-2 is now shown as Dr. Chen");
  await expect(form.getByText("Dr. Chen · speaker-2")).toBeVisible();
  await expect(form.getByText("speaker-2", { exact: true })).toBeVisible();

  await form.getByRole("button", { name: "Remove name" }).click();
  await expect(panel.getByRole("status")).toContainText("anonymous evidence ref remains");
  await expect(form.getByRole("code")).toHaveText("speaker-2");
});

test("speaker transcript represents overlap explicitly instead of flattening it", async ({ page }) => {
  const panel = await openTranscriptTools(page);

  await panel.getByRole("button", { name: "Open speaker transcript" }).click();
  const transcript = panel.getByRole("region", { name: "Speaker transcript" });
  await expect(transcript.getByText("Overlap", { exact: true })).toBeVisible();
  await expect(transcript.getByText("Participant A (speaker-1) + speaker-2")).toBeVisible();
  await expect(transcript.getByText("Yes, exactly.")).toBeVisible();
});

test("post-hoc publication chooses formats but never renders the destination path", async ({ page }) => {
  const panel = await openTranscriptTools(page);

  await panel.getByRole("checkbox", { name: "SubRip subtitles" }).check();
  await panel.getByRole("checkbox", { name: "WebVTT subtitles" }).check();
  await panel.getByRole("button", { name: "Choose folder and publish" }).click();

  await expect(panel.getByRole("status")).toContainText("Published 3 files");
  await expect(panel.getByRole("status")).toContainText("interview-42.txt");
  await expect(panel.getByRole("status")).toContainText("interview-42.srt");
  await expect(panel.getByRole("status")).toContainText("interview-42.vtt");
  await expect(panel.getByText(/\/Users\//)).toHaveCount(0);
});

test("publication requires at least one selected derived format", async ({ page }) => {
  const panel = await openTranscriptTools(page);

  await panel.getByRole("checkbox", { name: "Plain text" }).uncheck();
  await expect(panel.getByRole("button", { name: "Choose folder and publish" })).toBeDisabled();
});
