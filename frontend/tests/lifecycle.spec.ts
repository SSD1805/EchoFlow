import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

async function openStorage(page: import("@playwright/test").Page) {
  await page.goto("/?e2e=1");
  await page.getByRole("button", { name: "Storage" }).click();
  await expect(page.getByRole("heading", { name: "Storage & deletion" })).toBeVisible();
}

test("Scholion transcript deletion is previewed before application", async ({ page }) => {
  await openStorage(page);

  const transcript = page.getByRole("combobox", { name: "Transcript to manage" });
  await expect(transcript).toContainText("oral-history-42.m4a");

  await page
    .getByRole("checkbox", { name: /Delete the Scholion transcript/ })
    .check();
  await page.getByRole("button", { name: "Review what will be deleted" }).click();

  const plan = page.getByLabel("Deletion preview");
  await expect(
    plan.getByRole("heading", { name: "Review 4 items to be removed" }),
  ).toBeVisible();
  await expect(
    plan.getByText("Delete the Scholion transcript", { exact: true }),
  ).toBeVisible();
  await expect(plan.getByText(/2 notes will stay/)).toBeVisible();
  await plan.getByText("Why are extra items included?").click();
  await expect(
    plan.getByText(/Deleting a Scholion transcript also removes/),
  ).toBeVisible();

  await plan.getByRole("button", { name: "Delete these items" }).click();
  await expect(page.getByRole("status")).toContainText(
    "Deleted 4 items for interview-42",
  );
  await expect(transcript).not.toContainText("oral-history-42.m4a");
});

test("source deletion requires a second explicit guard and never exposes source paths", async ({
  page,
}) => {
  await openStorage(page);

  await page.getByRole("checkbox", { name: /Delete the original recording/ }).check();
  await expect(
    page.getByRole("button", { name: "Review what will be deleted" }),
  ).toBeDisabled();

  await page
    .getByRole("checkbox", { name: /I understand this deletes the original recording/ })
    .check();
  await page.getByRole("button", { name: "Review what will be deleted" }).click();

  await expect(page.getByLabel("Deletion preview")).toContainText(
    "Delete the original recording",
  );
  await expect(page.getByText(/forensic secure erasure/)).toBeVisible();
  await expect(page.getByText("source_path")).toHaveCount(0);
  await expect(page.getByText("canonical_path")).toHaveCount(0);
  await expect(page.getByText("/secret/")).toHaveCount(0);
});

test("cleanup preview separates completed work from resumable interrupted work", async ({
  page,
}) => {
  await openStorage(page);

  await page.getByRole("button", { name: "Preview cleanup" }).click();
  const firstPlan = page.getByLabel("Cleanup preview");
  await expect(firstPlan).toContainText("job-completed-2");
  await expect(firstPlan).not.toContainText("job-interrupted-7");
  await expect(firstPlan).toContainText("Last updated more than 30 days ago");

  await page
    .getByRole("checkbox", { name: /Also include failed and interrupted jobs/ })
    .check();
  await expect(firstPlan).toHaveCount(0);
  await page.getByRole("button", { name: "Preview cleanup" }).click();

  const secondPlan = page.getByLabel("Cleanup preview");
  await expect(secondPlan).toContainText("job-interrupted-7");
  await expect(secondPlan).toContainText("Saved progress will be lost");

  await secondPlan.getByRole("button", { name: "Remove these temporary files" }).click();
  await expect(page.getByRole("status")).toContainText(
    "Removed temporary processing files for 2 jobs",
  );
  await expect(
    page.getByText(/Finished transcripts and research were unchanged/),
  ).toBeVisible();
});

test("storage guidance and open deletion preview pass accessibility checks", async ({ page }) => {
  await openStorage(page);
  await page.getByRole("button", { name: "How storage controls work" }).click();
  await expect(
    page.getByRole("heading", { name: "Storage and deletion" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");

  await page.getByRole("checkbox", { name: /Remove from Library search/ }).check();
  await page.getByRole("button", { name: "Review what will be deleted" }).click();

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
});
