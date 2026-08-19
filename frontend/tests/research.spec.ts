import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

async function openResearch(page: import("@playwright/test").Page) {
  await page.goto("/?e2e=1");
  await page.getByRole("button", { name: "Research" }).click();
  await expect(page.getByRole("heading", { name: "Your research layer." })).toBeVisible();
}

test("Susan can browse authoritative research state without database knowledge", async ({
  page,
}) => {
  await openResearch(page);

  await expect(
    page.getByRole("heading", { name: "Notes", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Follow up on ABC governance during the next interview."),
  ).toBeVisible();
  await expect(page.getByText("Current evidence", { exact: true })).toBeVisible();
  await expect(page.getByText("Older evidence generation", { exact: true })).toBeVisible();

  await expect(
    page.getByRole("heading", { name: "Saved searches", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Governance follow-up")).toBeVisible();
  await expect(page.getByText("Questions to revisit across interviews")).toBeVisible();
  await expect(page.getByText("#governance")).toBeVisible();
  await expect(page.getByText("Oral histories", { exact: true }).first()).toBeVisible();

  await expect(page.getByText("/Users/")).toHaveCount(0);
  await expect(page.getByText("canonical_path")).toHaveCount(0);
  await expect(page.getByText("source_path")).toHaveCount(0);

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("research workspace refresh remains keyboard reachable", async ({ page }) => {
  await openResearch(page);

  const refresh = page.getByRole("button", { name: "Refresh research" });
  await refresh.focus();
  await expect(refresh).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toContainText("2 notes");
});
