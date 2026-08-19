import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

async function openLibrary(page: import("@playwright/test").Page) {
  await page.goto("/?e2e=1");
  await page.getByRole("button", { name: "Library" }).click();
  await expect(page.getByRole("heading", { name: "Search your evidence." })).toBeVisible();
}

test("Susan can search grouped evidence and research state", async ({ page }) => {
  await openLibrary(page);

  const search = page.getByRole("searchbox", { name: "Search EchoFlow" });
  await search.fill("ABC");
  await page.getByRole("button", { name: "Search", exact: true }).click();

  await expect(page.getByRole("heading", { name: "Evidence", exact: true })).toBeVisible();
  await expect(page.getByText("We started the ABC program after the second interview round.")).toBeVisible();
  await expect(page.getByText("Verified seek point")).toBeVisible();
  await expect(page.locator("[data-seek-seconds='862.43']")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Notes", exact: true })).toBeVisible();
  await expect(page.getByText("Follow up on ABC governance during the next interview.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Tags", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Collections", exact: true })).toBeVisible();
  await expect(page.getByText("DuckDB")).toHaveCount(0);
  await expect(page.getByText("SQLite")).toHaveCount(0);
});

test("workspace search is keyboard reachable and accessible after results render", async ({ page }) => {
  await openLibrary(page);

  await page.keyboard.press("Control+K");
  const search = page.getByRole("searchbox", { name: "Search EchoFlow" });
  await expect(search).toBeFocused();
  await search.fill("ABC");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toContainText("4 results");

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("transcript and note markup remains inert text", async ({ page }) => {
  await openLibrary(page);

  const hostile = "<img src=x onerror=alert(1)>";
  await page.getByRole("searchbox", { name: "Search EchoFlow" }).fill(hostile);
  await page.getByRole("button", { name: "Search", exact: true }).click();

  await expect(page.getByText(`We started the ${hostile} program after the second interview round.`)).toBeVisible();
  await expect(page.getByText(`Follow up on ${hostile} governance during the next interview.`)).toBeVisible();
  await expect(page.locator(".result-groups img")).toHaveCount(0);
});
