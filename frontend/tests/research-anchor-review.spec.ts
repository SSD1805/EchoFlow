import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

async function openResearch(page: import("@playwright/test").Page) {
  await page.goto("/?e2e=1");
  await page.getByRole("button", { name: "Research" }).click();
  await expect(page.getByRole("heading", { name: "Research", exact: true })).toBeVisible();
}

test("Susan can review an earlier transcript link before deliberately moving a note", async ({
  page,
}) => {
  await openResearch(page);

  const maintenance = page.getByRole("region", {
    name: "Review notes tied to earlier transcript versions",
  });
  await expect(maintenance).toBeVisible();
  await expect(maintenance).toContainText(
    "Scholion never silently moves a note when a transcript changes.",
  );

  const card = maintenance
    .locator(".research-anchor-card")
    .filter({ hasText: "Earlier interpretation retained for provenance." });
  await card.getByRole("button", { name: "Compare transcript versions" }).click();

  await expect(card).toContainText(
    "This note still points to a valid earlier transcript version.",
  );
  await expect(card.getByRole("region", { name: "Passage this note points to" })).toBeVisible();
  await expect(card.getByRole("region", { name: "Current transcript passage" })).toBeVisible();
  await expect(card).not.toContainText("/Users/");
  await expect(card).not.toContainText("canonical_path");
  await expect(card).not.toContainText("source_path");

  await card.getByRole("button", { name: "Move note to this passage" }).click();
  const confirmation = card.getByRole("group", { name: "Confirm note move" });
  await expect(confirmation).toContainText(
    "Its earlier transcript link will remain in the note's history.",
  );
  await confirmation
    .getByRole("button", { name: "Confirm move to current transcript" })
    .click();

  await expect(
    maintenance.getByText(
      "Note moved to the reviewed passage in the current transcript. Its earlier transcript link was kept in the note's history.",
    ),
  ).toBeVisible();

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
