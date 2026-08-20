import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

async function openTypedSearch(page: import("@playwright/test").Page) {
  await page.goto("/?e2e=1");
  await page.getByRole("button", { name: "Research" }).click();
  const panel = page.getByRole("region", { name: "Make the question inspectable." });
  await expect(panel).toBeVisible();
  return panel;
}

test("typed Research search keeps advanced intent inspectable and evidence navigable", async ({
  page,
}) => {
  const panel = await openTypedSearch(page);

  await panel.getByLabel("Query").fill("governance reform");
  await panel.getByLabel("Exact phrase").check();
  await panel.getByLabel("Term operator").selectOption("all");
  await panel.getByLabel("Retrieval mode").selectOption("lexical");
  await panel.getByLabel("Sort").selectOption("timeline");
  await panel.getByLabel("Result limit").fill("25");
  await panel.getByLabel("Context segments").fill("2");
  await panel.getByLabel("Speaker refs").fill("speaker-1");
  await panel.getByLabel("Languages").fill("en");
  await panel.getByLabel("Transcript IDs").fill("interview-42");
  await panel.getByLabel("Tags").fill("governance");
  await panel.getByLabel("Collections").fill("Oral histories");
  await panel.getByLabel("Note text").fill("follow up");
  await panel.getByLabel("Require associated research notes").check();

  await panel.getByRole("button", { name: "Run typed search" }).click();

  const applied = panel.getByLabel("Applied search intent").first();
  await expect(applied).toContainText("governance reform");
  await expect(applied).toContainText("exact phrase");
  await expect(applied).toContainText("mode: lexical");
  await expect(applied).toContainText("sort: timeline");
  await expect(applied).toContainText("speaker: speaker-1");
  await expect(applied).toContainText("language: en");
  await expect(applied).toContainText("transcript: interview-42");
  await expect(applied).toContainText("tag: governance");
  await expect(applied).toContainText("collection: Oral histories");
  await expect(applied).toContainText("note text: follow up");
  await expect(applied).toContainText("must have research notes");

  await expect(panel.getByText("Retrieval provenance")).toBeVisible();
  const results = panel.getByLabel("Typed search evidence results");
  await expect(results).toContainText("interview-42");
  await results.getByRole("button", { name: "Open verified evidence" }).click();
  const reader = page.getByRole("complementary", { name: "Evidence reader" });
  await expect(reader.getByText("Current verified canonical generation")).toBeVisible();
  await reader.getByRole("button", { name: "Close" }).click();

  await expect(page.getByText("canonical_path")).toHaveCount(0);
  await expect(page.getByText("source_path")).toHaveCount(0);
  await expect(page.getByText("/Users/")).toHaveCount(0);

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
});

test("saved Research questions can replace their whole typed intent", async ({ page }) => {
  const panel = await openTypedSearch(page);

  const savedList = panel.getByLabel("Saved searches available to edit");
  await savedList.getByRole("button", { name: /Governance follow-up/ }).click();
  const existing = panel.getByLabel("Applied search intent");
  await expect(existing).toContainText("governance");
  await expect(existing).toContainText("tag: governance");
  await expect(existing).toContainText("must have research notes");

  await panel.getByLabel("Query").fill("oversight failure");
  await panel.getByLabel("Term operator").selectOption("all");
  await panel.getByLabel("Sort").selectOption("timeline");
  await panel.getByLabel("Languages").fill("en, fr");
  await panel.getByLabel("Tags").fill("oversight, governance");
  await panel.getByLabel("Name").fill("Oversight follow-up");
  await panel.getByLabel("Description").fill("Revised durable question");
  await panel
    .getByRole("button", { name: "Save metadata + typed intent" })
    .click();

  await expect(panel).toContainText(
    "Display metadata and typed query intent committed together.",
  );
  const updated = panel.getByLabel("Applied search intent");
  await expect(updated).toContainText("oversight failure");
  await expect(updated).toContainText("terms: ALL");
  await expect(updated).toContainText("sort: timeline");
  await expect(updated).toContainText("language: en");
  await expect(updated).toContainText("language: fr");
  await expect(updated).toContainText("tag: oversight");
  await expect(updated).toContainText("tag: governance");
  await expect(savedList.getByRole("button", { name: /Oversight follow-up/ })).toBeVisible();

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
});
