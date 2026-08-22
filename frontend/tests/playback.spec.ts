import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

async function openLibraryEvidence(
  page: import("@playwright/test").Page,
  query = "?e2e=1",
) {
  await page.goto(`/${query}`);
  await page.getByRole("button", { name: "Library" }).click();
  await page.getByRole("searchbox", { name: "Search Scholion" }).fill("ABC");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.getByRole("button", { name: /Open transcript passage from interview-42/ }).click();
  return page.getByRole("complementary", { name: "Evidence reader" });
}

test("playback starts from the transcript position without path disclosure", async ({
  page,
}) => {
  const reader = await openLibraryEvidence(page);
  const playback = reader.getByRole("region", { name: "Playback" });

  await expect(playback.getByText(/Playback stays on this computer/)).toBeVisible();
  await playback.getByRole("button", { name: "Prepare playback" }).click();

  await expect(playback.getByRole("status")).toHaveText(
    "Playback ready at 14:22.",
  );
  await expect(playback.locator("[data-session-seek-seconds='862.43']")).toBeVisible();
  await expect(playback.getByLabel("Original recording audio")).toBeVisible();
  await expect(reader.getByText("/Users/")).toHaveCount(0);
  await expect(reader.getByText("source_path")).toHaveCount(0);
  await expect(reader.getByText("canonical_path")).toHaveCount(0);

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
});

test("word-level transcript position is the coordinate submitted to playback", async ({
  page,
}) => {
  const reader = await openLibraryEvidence(page);
  await reader
    .getByRole("button", { name: /Move recording position to 14:22 at started/ })
    .click();
  const playback = reader.getByRole("region", { name: "Playback" });

  await playback.getByRole("button", { name: "Prepare playback" }).click();

  await expect(playback.locator("[data-session-seek-seconds='862.35']")).toBeVisible();
  await expect(reader.locator("[data-playhead-seconds='862.35']")).toBeVisible();
});

for (const [mode, expected] of [
  ["missing", "Original recording is unavailable at its recorded location"],
  ["changed", "Original recording no longer matches the source used for this transcript"],
  [
    "multi-audio",
    "Playback for recordings with multiple audio streams is not enabled yet; Scholion will not guess which track matches this transcript",
  ],
] as const) {
  test(`playback ${mode} failure is explicit and never creates a media session`, async ({
    page,
  }) => {
    const reader = await openLibraryEvidence(page, `?e2e=1&playback=${mode}`);
    const playback = reader.getByRole("region", { name: "Playback" });

    await playback.getByRole("button", { name: "Prepare playback" }).click();

    await expect(playback.getByRole("alert")).toHaveText(expected);
    await expect(playback.locator("audio, video")).toHaveCount(0);
    await expect(reader.getByText("/Users/")).toHaveCount(0);
  });
}

test("video evidence uses the same checked playback contract", async ({ page }) => {
  const reader = await openLibraryEvidence(page, "?e2e=1&media=video");
  const playback = reader.getByRole("region", { name: "Playback" });

  await playback.getByRole("button", { name: "Prepare playback" }).click();

  await expect(playback.getByLabel("Original recording video")).toBeVisible();
  await expect(playback.locator("[data-media-kind='video']")).toBeVisible();
});

test("earlier transcript evidence can request playback for its exact preserved version", async ({
  page,
}) => {
  await page.goto("/?e2e=1");
  await page.getByRole("button", { name: "Research" }).click();
  await expect(page.getByRole("heading", { name: "Research", exact: true })).toBeVisible();
  const oldNote = page.locator(".research-note-card").filter({ hasText: "interview-11" });
  await oldNote.getByRole("button", { name: "Open transcript passage" }).click();
  const reader = page.getByRole("complementary", { name: "Evidence reader" });
  await expect(reader.getByText(/Earlier transcript version ·/)).toBeVisible();

  const playback = reader.getByRole("region", { name: "Playback" });
  await playback.getByRole("button", { name: "Prepare playback" }).click();

  await expect(playback.getByRole("status")).toContainText("Playback ready");
  await expect(reader.getByText("cccccccccccc…")).toBeVisible();
  await expect(reader.getByText("source_path")).toHaveCount(0);
});

test("playback preparation remains keyboard reachable", async ({ page }) => {
  const reader = await openLibraryEvidence(page);
  const prepare = reader.getByRole("button", { name: "Prepare playback" });

  await prepare.focus();
  await page.keyboard.press("Enter");

  await expect(reader.getByRole("region", { name: "Playback" }).getByRole("status")).toContainText(
    "Playback ready",
  );
});
