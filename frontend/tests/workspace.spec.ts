import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

async function openLibrary(page: import("@playwright/test").Page) {
  await page.goto("/?e2e=1");
  await page.getByRole("button", { name: "Library" }).click();
  await expect(page.getByRole("heading", { name: "Search your evidence." })).toBeVisible();
}

async function searchWorkspace(
  page: import("@playwright/test").Page,
  query = "ABC",
) {
  const search = page.getByRole("searchbox", { name: "Search EchoFlow" });
  await search.fill(query);
  await page.getByRole("button", { name: "Search", exact: true }).click();
}

test("Susan can search grouped evidence and research state", async ({ page }) => {
  await openLibrary(page);
  await searchWorkspace(page);

  await expect(page.getByRole("heading", { name: "Evidence", exact: true })).toBeVisible();
  await expect(
    page.getByText("We started the ABC program after the second interview round."),
  ).toBeVisible();
  await expect(page.getByText("Verified seek point")).toBeVisible();
  await expect(page.locator("[data-seek-seconds='862.43']")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Notes", exact: true })).toBeVisible();
  await expect(
    page.getByText("Follow up on ABC governance during the next interview."),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Tags", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Collections", exact: true })).toBeVisible();
  await expect(page.getByText("DuckDB")).toHaveCount(0);
  await expect(page.getByText("SQLite")).toHaveCount(0);
});

test("Susan can open a verified transcript window from a search result", async ({ page }) => {
  await openLibrary(page);
  await searchWorkspace(page);

  await page.getByRole("button", { name: /Open verified evidence from interview-42/ }).click();

  const reader = page.getByRole("complementary", { name: "Evidence reader" });
  await expect(reader).toBeVisible();
  await expect(reader.getByText("interview-42")).toBeVisible();
  await expect(reader.getByText("aaaaaaaaaaaa…")).toBeVisible();
  await expect(
    reader.getByText("We had already completed two rounds of interviews."),
  ).toBeVisible();
  await expect(
    reader.getByText("The first cohort joined the following month."),
  ).toBeVisible();
  await expect(reader.locator("mark")).toHaveText("ABC");
  await expect(reader.locator("[data-seek-seconds='862.43']")).toContainText("14:22");

  await expect(reader.getByText("/Users/")).toHaveCount(0);
  await expect(reader.getByText("canonical_path")).toHaveCount(0);
  await expect(reader.getByText("source_path")).toHaveCount(0);

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("workspace search is keyboard reachable and accessible after results render", async ({
  page,
}) => {
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
  await searchWorkspace(page, hostile);

  await expect(
    page.getByText(`We started the ${hostile} program after the second interview round.`),
  ).toBeVisible();
  await expect(
    page.getByText(`Follow up on ${hostile} governance during the next interview.`),
  ).toBeVisible();
  await expect(page.locator(".result-groups img")).toHaveCount(0);

  await page.getByRole("button", { name: /Open verified evidence from interview-42/ }).click();
  const reader = page.getByRole("complementary", { name: "Evidence reader" });
  await expect(reader.locator("mark")).toHaveText(hostile);
  await expect(reader.locator("img")).toHaveCount(0);
});
