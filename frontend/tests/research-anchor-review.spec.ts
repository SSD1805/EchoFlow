import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

async function openResearch(page: import("@playwright/test").Page) {
  await page.goto("/?e2e=1");
  await page.getByRole("button", { name: "Research" }).click();
  await expect(page.getByRole("heading", { name: "Research", exact: true })).toBeVisible();
}

test("Susan can review an older anchor before deliberately re-anchoring it", async ({
  page,
}) => {
  await openResearch(page);

  const maintenance = page.getByRole("region", {
    name: "Review older or unavailable note anchors",
  });
  await expect(maintenance).toBeVisible();
  await expect(maintenance).toContainText(
    "EchoFlow never silently moves research to a newer transcript.",
  );

  const card = maintenance
    .locator(".research-anchor-card")
    .filter({ hasText: "Earlier interpretation retained for provenance." });
  await card.getByRole("button", { name: "Review evidence status" }).click();

  await expect(card).toContainText(
    "The stored evidence still verifies, but it belongs to an older canonical generation.",
  );
  await expect(card.getByRole("region", { name: "Stored anchor" })).toContainText(
    "Earlier verified evidence.",
  );
  await expect(card.getByRole("region", { name: "Current candidate" })).toContainText(
    "Current reviewed evidence.",
  );
  await expect(card).not.toContainText("/Users/");
  await expect(card).not.toContainText("canonical_path");
  await expect(card).not.toContainText("source_path");

  await card.getByRole("button", { name: "Prepare re-anchor" }).click();
  const confirmation = card.getByRole("group", { name: "Confirm re-anchor" });
  await expect(confirmation).toContainText(
    "The existing anchor will be retained as immutable history.",
  );
  await confirmation
    .getByRole("button", { name: "Confirm re-anchor to reviewed candidate" })
    .click();

  await expect(
    maintenance.getByText(
      "Note re-anchored to the reviewed current generation. The prior anchor was preserved in durable history.",
    ),
  ).toBeVisible();

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
