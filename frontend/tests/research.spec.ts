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

  const notes = page.getByLabel("Notes", { exact: true });
  await expect(notes.getByRole("heading", { name: "Notes", exact: true })).toBeVisible();
  await expect(
    notes.getByText("Follow up on ABC governance during the next interview."),
  ).toBeVisible();
  await expect(notes.getByText("Current evidence", { exact: true })).toBeVisible();
  await expect(notes.getByText("Older evidence generation", { exact: true })).toBeVisible();
  await expect(notes.getByText("#governance", { exact: true })).toBeVisible();

  await expect(
    page.getByRole("heading", { name: "Saved searches", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Governance follow-up")).toBeVisible();
  await expect(page.getByText("Questions to revisit across interviews")).toBeVisible();

  const navigation = page.getByLabel("Research navigation");
  await expect(navigation.getByText("#governance", { exact: true })).toBeVisible();
  await expect(navigation.getByText("Oral histories", { exact: true })).toBeVisible();

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

test("Susan can edit labels and explicitly delete a durable research note", async ({
  page,
}) => {
  await openResearch(page);

  const noteCard = page.locator(".research-note-card").filter({
    hasText: "interview-42",
  });
  await noteCard.getByRole("button", { name: "Edit note" }).click();
  await noteCard
    .getByLabel("Note text for interview-42")
    .fill("Compare governance with the follow-up interview.");
  await noteCard.getByLabel("Tags for interview-42").fill("program, follow-up");
  await noteCard
    .getByLabel("Collections for interview-42")
    .fill("Oral histories, Chapter 3");
  await noteCard.getByRole("button", { name: "Save note" }).click();

  await expect(
    page.getByText("Note saved. Its verified evidence anchor is unchanged."),
  ).toBeVisible();
  await expect(
    noteCard.getByText("Compare governance with the follow-up interview."),
  ).toBeVisible();
  await expect(noteCard.getByText("#follow-up", { exact: true })).toBeVisible();
  await expect(noteCard.getByText("Chapter 3", { exact: true })).toBeVisible();

  await noteCard.getByRole("button", { name: "Delete note" }).click();
  await expect(noteCard.getByLabel("Delete note confirmation")).toContainText(
    "canonical transcript and original recording are not part of this operation",
  );
  await noteCard.getByRole("button", { name: "Delete note permanently" }).click();

  await expect(
    page.getByText("Note deleted. Transcript evidence was not deleted."),
  ).toBeVisible();
  await expect(
    page.getByText("Compare governance with the follow-up interview."),
  ).toHaveCount(0);

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
