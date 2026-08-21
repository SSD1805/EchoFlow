import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

async function openStorage(page: import("@playwright/test").Page) {
  await page.goto("/?e2e=1");
  await page.getByRole("button", { name: "Storage" }).click();
  await expect(page.getByRole("heading", { name: "Storage & deletion" })).toBeVisible();
}

test("canonical deletion is previewed before backend-bound application", async ({ page }) => {
  await openStorage(page);

  const transcript = page.getByRole("combobox", { name: "Transcript to manage" });
  await expect(transcript).toContainText("oral-history-42.m4a");

  await page
    .getByRole("checkbox", { name: /Delete canonical transcript evidence/ })
    .check();
  await page.getByRole("button", { name: "Preview deletion plan" }).click();

  const plan = page.getByLabel("Deletion plan");
  await expect(
    plan.getByRole("heading", { name: "Review 4 planned actions" }),
  ).toBeVisible();
  await expect(plan.getByText("delete canonical transcript evidence")).toBeVisible();
  await expect(plan.getByText(/2 anchored notes preserved/)).toBeVisible();
  await plan.getByText("Why did EchoFlow expand my selection?").click();
  await expect(
    plan.getByText(/Canonical transcript deletion automatically includes/),
  ).toBeVisible();

  await plan.getByRole("button", { name: "Apply reviewed plan" }).click();
  await expect(page.getByRole("status")).toContainText(
    "Applied custody plan for interview-42",
  );
  await expect(transcript).not.toContainText("oral-history-42.m4a");
});

test("source deletion requires a second explicit guard and never exposes source paths", async ({
  page,
}) => {
  await openStorage(page);

  await page.getByRole("checkbox", { name: /Delete the original recording/ }).check();
  await expect(
    page.getByRole("button", { name: "Preview deletion plan" }),
  ).toBeDisabled();

  await page
    .getByRole("checkbox", { name: /I understand this deletes the original recording/ })
    .check();
  await page.getByRole("button", { name: "Preview deletion plan" }).click();

  await expect(page.getByLabel("Deletion plan")).toContainText(
    "delete the original source recording",
  );
  await expect(page.getByText(/forensic secure erasure/)).toBeVisible();
  await expect(page.getByText("source_path")).toHaveCount(0);
  await expect(page.getByText("canonical_path")).toHaveCount(0);
  await expect(page.getByText("/secret/")).toHaveCount(0);
});

test("retention preview separates completed cleanup from resumable interrupted work", async ({
  page,
}) => {
  await openStorage(page);

  await page.getByRole("button", { name: "Preview cleanup" }).click();
  const firstPlan = page.getByLabel("Retention plan");
  await expect(firstPlan).toContainText("job-completed-2");
  await expect(firstPlan).not.toContainText("job-interrupted-7");

  await page
    .getByRole("checkbox", { name: /Also include failed and interrupted jobs/ })
    .check();
  await expect(firstPlan).toHaveCount(0);
  await page.getByRole("button", { name: "Preview cleanup" }).click();

  const secondPlan = page.getByLabel("Retention plan");
  await expect(secondPlan).toContainText("job-interrupted-7");
  await expect(secondPlan).toContainText("Resume will be lost");

  await secondPlan.getByRole("button", { name: "Apply cleanup plan" }).click();
  await expect(page.getByRole("status")).toContainText(
    "Removed private processing state for 2 jobs",
  );
  await expect(
    page.getByText(/Canonical evidence and human research were outside this operation/),
  ).toBeVisible();
});

test("storage guidance and open plan pass accessibility checks", async ({ page }) => {
  await openStorage(page);
  await page.getByRole("button", { name: "How storage controls work" }).click();
  await expect(
    page.getByRole("heading", { name: "Storage and lifecycle controls" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");

  await page.getByRole("checkbox", { name: /Remove from Library search/ }).check();
  await page.getByRole("button", { name: "Preview deletion plan" }).click();

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
});
