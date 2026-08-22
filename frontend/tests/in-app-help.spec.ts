import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

async function openLibraryResult(page: import("@playwright/test").Page) {
  await page.goto("/?e2e=1");
  await page.getByRole("button", { name: "Library" }).click();
  await page.getByRole("searchbox", { name: "Search Scholion" }).fill("ABC");
  await page.getByRole("button", { name: "Search", exact: true }).click();
}

test("workspace help remains discoverable and follows the current screen", async ({
  page,
}) => {
  await page.goto("/?e2e=1");
  const screenHelp = page.getByRole("button", { name: "How this screen works" });

  await expect(screenHelp).toHaveAttribute("aria-expanded", "false");
  await screenHelp.click();
  await expect(page.getByRole("heading", { name: "Adding files" })).toBeVisible();
  await expect(page.getByText(/Selecting something does not copy, transcribe, or remove it/)).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(screenHelp).toHaveAttribute("aria-expanded", "false");
  await expect(screenHelp).toBeFocused();

  await page.getByRole("button", { name: "Processing" }).click();
  await screenHelp.click();
  await expect(page.getByRole("heading", { name: "Transcribing recordings" })).toBeVisible();
  await expect(page.getByText(/Resume continues saved progress/)).toBeVisible();
  await expect(page.getByText(/does not send this information or telemetry anywhere/)).toBeVisible();
});

test("global help explains durable files without exposing implementation paths", async ({
  page,
}) => {
  await page.goto("/?e2e=1");
  await page.getByRole("button", { name: "How Scholion works" }).click();

  await expect(page.getByRole("heading", { name: "How Scholion works" })).toBeVisible();
  await expect(page.getByText(/Original recordings and Scholion transcripts are durable files/)).toBeVisible();
  await expect(page.getByText("source_path")).toHaveCount(0);
  await expect(page.getByText("canonical_path")).toHaveCount(0);

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
});

test("transcript reader playback and speaker tools carry help at the point of use", async ({
  page,
}) => {
  await openLibraryResult(page);
  await page
    .getByRole("button", { name: /Open transcript passage from interview-42/ })
    .click();

  const reader = page.getByRole("complementary", { name: "Evidence reader" });
  await reader.getByRole("button", { name: "How to use this" }).click();
  await expect(page.getByRole("heading", { name: "Using the transcript reader" })).toBeVisible();
  await expect(page.getByText(/Select a timed word/)).toBeVisible();

  const playback = reader.getByRole("region", { name: "Playback" });
  await playback.getByRole("button", { name: "Why check?" }).click();
  await expect(page.getByRole("heading", { name: "Playing the original recording" })).toBeVisible();
  await expect(page.getByText(/Recordings with multiple audio tracks are not played automatically yet/)).toBeVisible();

  await reader.getByRole("button", { name: "Close", exact: true }).click();
  await page.getByRole("button", { name: /Open speaker and export tools for interview-42/ }).click();
  const tools = page.getByRole("complementary", { name: "Transcript tools" });
  await tools.getByRole("button", { name: "How these work" }).click();
  await expect(
    page.getByRole("heading", { name: "Transcript and speaker tools" }),
  ).toBeVisible();
  await expect(page.getByText(/Speaker names are your own display labels/)).toBeVisible();

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
});
