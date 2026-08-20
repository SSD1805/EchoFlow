import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

async function openResearchSearch(page: import("@playwright/test").Page) {
  await page.goto("/?e2e=1");
  await page.getByRole("button", { name: "Research" }).click();
  const panel = page.getByRole("region", { name: "What are you looking for?" });
  await expect(panel).toBeVisible();
  return panel;
}

test("Research search exposes human choices while preserving advanced intent", async ({ page }) => {
  const panel = await openResearchSearch(page);

  await panel.getByRole("searchbox", { name: "Search", exact: true }).fill("governance reform");
  await panel.getByLabel("Match").selectOption("phrase");
  await panel.getByText("Search options", { exact: true }).click();
  await panel.getByLabel("Search by").selectOption("lexical");
  await panel.getByLabel("Order results by").selectOption("timeline");
  await panel.getByLabel("Maximum results").fill("25");
  await panel.getByLabel("Context around result").fill("2");
  await panel.getByLabel("Speakers").fill("speaker-1");
  await panel.getByLabel("Languages").fill("en");
  await panel.getByLabel("Interviews or transcripts").fill("interview-42");
  await panel.getByLabel("Tags").fill("governance");
  await panel.getByLabel("Collections").fill("Oral histories");
  await panel.getByLabel("Notes containing").fill("follow up");
  await panel.getByLabel("Only results with notes").check();

  await panel.getByRole("button", { name: "Search", exact: true }).click();

  const applied = panel.getByLabel("Search details").first();
  await expect(applied).toContainText("governance reform");
  await expect(applied).toContainText("Match: Exact phrase");
  await expect(applied).toContainText("Search by: Wording");
  await expect(applied).toContainText("Order: Time");
  await expect(applied).toContainText("Speaker: speaker-1");
  await expect(applied).toContainText("Language: en");
  await expect(applied).toContainText("Transcript: interview-42");
  await expect(applied).toContainText("Tag: governance");
  await expect(applied).toContainText("Collection: Oral histories");
  await expect(applied).toContainText("Notes containing: follow up");
  await expect(applied).toContainText("Only results with notes");

  await panel.getByText("Technical details", { exact: true }).click();
  await expect(panel.getByText("Retrieval", { exact: true })).toBeVisible();
  const results = panel.getByLabel("Research search results");
  await expect(results).toContainText("interview-42");
  await results.getByRole("button", { name: "Open evidence" }).click();
  const reader = page.getByRole("complementary", { name: "Evidence reader" });
  await expect(reader.getByText("Current verified canonical generation")).toBeVisible();
  await reader.getByRole("button", { name: "Close" }).click();

  await expect(panel.getByText("Python authority")).toHaveCount(0);
  await expect(panel.getByText("Term operator")).toHaveCount(0);
  await expect(page.getByText("canonical_path")).toHaveCount(0);
  await expect(page.getByText("source_path")).toHaveCount(0);
  await expect(page.getByText("/Users/")).toHaveCount(0);

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
});

test("saved Research questions can replace the whole search without backend vocabulary", async ({ page }) => {
  const panel = await openResearchSearch(page);

  const savedList = panel.getByLabel("Saved searches");
  await savedList.getByRole("button", { name: /Governance follow-up/ }).click();
  const existing = panel.getByLabel("Search details");
  await expect(existing).toContainText("governance");
  await expect(existing).toContainText("Tag: governance");
  await expect(existing).toContainText("Only results with notes");

  await panel.getByRole("searchbox", { name: "Search", exact: true }).fill("oversight failure");
  await panel.getByLabel("Match").selectOption("all");
  await panel.getByText("Search options", { exact: true }).click();
  await panel.getByLabel("Order results by").selectOption("timeline");
  await panel.getByLabel("Languages").fill("en, fr");
  await panel.getByLabel("Tags").fill("oversight, governance");
  await panel.getByLabel("Name").fill("Oversight follow-up");
  await panel.getByLabel("Description").fill("Revised durable question");
  await panel.getByRole("button", { name: "Update saved search" }).click();

  await expect(panel.locator(".typed-search-status")).toContainText("Updated “Oversight follow-up”");
  const updated = panel.getByLabel("Search details");
  await expect(updated).toContainText("oversight failure");
  await expect(updated).toContainText("Match: All of these words");
  await expect(updated).toContainText("Order: Time");
  await expect(updated).toContainText("Language: en");
  await expect(updated).toContainText("Language: fr");
  await expect(updated).toContainText("Tag: oversight");
  await expect(updated).toContainText("Tag: governance");
  await expect(savedList.getByRole("button", { name: /Oversight follow-up/ })).toBeVisible();

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
});
