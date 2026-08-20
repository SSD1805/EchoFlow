import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

async function openResearch(page: import("@playwright/test").Page) {
  await page.goto("/?e2e=1");
  await page.getByRole("button", { name: "Research" }).click();
  await expect(page.getByRole("heading", { name: "Research", exact: true })).toBeVisible();
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
  await expect(notes.getByRole("button", { name: "#governance" })).toBeVisible();

  await expect(
    page.getByRole("heading", { name: "Saved searches", exact: true }),
  ).toBeVisible();
  const navigation = page.getByLabel("Research navigation");
  await expect(navigation.getByText("Governance follow-up")).toBeVisible();
  await expect(
    navigation.getByText("Questions to revisit across interviews"),
  ).toBeVisible();
  await expect(navigation.getByRole("button", { name: "#governance" })).toBeVisible();
  await expect(navigation.getByRole("button", { name: "Oral histories" })).toBeVisible();

  await expect(page.getByText("Human knowledge stays human knowledge")).toHaveCount(0);
  await expect(page.getByText("authoritative annotations", { exact: false })).toHaveCount(0);
  await expect(page.getByText("durable questions", { exact: false })).toHaveCount(0);
  await expect(page.getByText("/Users/")).toHaveCount(0);
  await expect(page.getByText("canonical_path")).toHaveCount(0);
  await expect(page.getByText("source_path")).toHaveCount(0);

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("research workspace refresh remains keyboard reachable", async ({ page }) => {
  await openResearch(page);

  const refresh = page.getByRole("button", { name: "Refresh", exact: true });
  await refresh.focus();
  await expect(refresh).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toContainText("2 notes");
});

test("Susan can filter by durable labels and return to verified evidence", async ({ page }) => {
  await openResearch(page);

  const notes = page.getByLabel("Notes", { exact: true });
  const tags = page.getByRole("group", { name: "Research tags" });
  await tags.getByRole("button", { name: "#governance" }).click();

  const active = page.getByRole("region", { name: "Active research filters" });
  await expect(active).toContainText("Every selected label must match the same note.");
  await expect(active.getByRole("button", { name: "Remove tag governance" })).toBeVisible();
  await expect(
    notes.getByText("Follow up on ABC governance during the next interview."),
  ).toBeVisible();
  await expect(
    notes.getByText("Earlier interpretation retained for provenance."),
  ).toHaveCount(0);

  await tags.getByRole("button", { name: "#program" }).click();
  await expect(active.getByRole("button", { name: "Remove tag program" })).toBeVisible();
  await expect(
    page.getByText("Showing 1 note matching every selected label."),
  ).toBeVisible();

  const collections = page.getByRole("group", { name: "Research collections" });
  await collections.getByRole("button", { name: "Oral histories" }).click();
  await expect(
    active.getByRole("button", { name: "Remove collection Oral histories" }),
  ).toBeVisible();

  const filteredNote = page
    .locator(".research-note-card")
    .filter({ hasText: "interview-42" });
  await filteredNote.getByRole("button", { name: "Open verified evidence" }).click();
  const reader = page.getByRole("complementary", { name: "Evidence reader" });
  await expect(reader.getByText("Current verified canonical generation")).toBeVisible();
  await reader.getByRole("button", { name: "Close" }).click();

  await active.getByRole("button", { name: "Clear filters" }).click();
  await expect(
    notes.getByText("Earlier interpretation retained for provenance."),
  ).toBeVisible();

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
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
    page.getByText("Note saved. Its transcript passage is unchanged."),
  ).toBeVisible();
  await expect(
    noteCard.getByText("Compare governance with the follow-up interview."),
  ).toBeVisible();
  await expect(noteCard.getByRole("button", { name: "#follow-up" })).toBeVisible();
  await expect(noteCard.getByRole("button", { name: "Chapter 3" })).toBeVisible();

  await noteCard.getByRole("button", { name: "Delete note" }).click();
  await expect(noteCard.getByLabel("Delete note confirmation")).toContainText(
    "This does not delete the transcript or original recording",
  );
  await noteCard.getByRole("button", { name: "Delete note permanently" }).click();

  await expect(
    page.getByText("Note deleted. The transcript was not deleted."),
  ).toBeVisible();
  await expect(
    page.getByText("Compare governance with the follow-up interview."),
  ).toHaveCount(0);

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("Susan can reopen a note against its exact older canonical generation", async ({
  page,
}) => {
  await openResearch(page);

  const oldNote = page.locator(".research-note-card").filter({ hasText: "interview-11" });
  await oldNote.getByRole("button", { name: "Open verified evidence" }).click();

  const reader = page.getByRole("complementary", { name: "Evidence reader" });
  await expect(reader).toBeVisible();
  await expect(reader.getByText(/Older verified canonical generation/)).toBeVisible();
  await expect(reader.getByText("Anchored evidence", { exact: true })).toBeVisible();
  await expect(reader.getByText("cccccccccccc…")).toBeVisible();
  await expect(reader.getByText("Preserved research evidence")).toBeVisible();
  await expect(reader.getByRole("heading", { name: "Attach a note to this evidence" })).toHaveCount(0);
  await expect(
    page.getByText("Opened the exact older transcript version cited by this note. Nothing was moved."),
  ).toBeVisible();
  await expect(page.getByText("/Users/")).toHaveCount(0);
  await expect(page.getByText("canonical_path")).toHaveCount(0);
  await expect(page.getByText("source_path")).toHaveCount(0);

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});

test("Susan can create rename run and delete durable saved-search intent", async ({ page }) => {
  await openResearch(page);

  await page.getByLabel("Saved search name").fill("Methods sweep");
  await page.getByLabel("Saved search query").fill("methodology");
  await page.getByLabel("Saved search description").fill("Questions across current interviews");
  await page.getByRole("button", { name: "Save search" }).click();
  await expect(page.getByText("Methods sweep", { exact: true })).toBeVisible();

  const initialSavedCard = page
    .locator(".saved-search-list article")
    .filter({ hasText: "methodology" });
  await initialSavedCard.getByRole("button", { name: "Rename" }).click();

  const savedEditor = page.locator(".saved-search-editor");
  await savedEditor
    .getByLabel("Saved search name for methodology")
    .fill("Methods follow-up");
  await savedEditor.getByRole("button", { name: "Save name" }).click();

  const savedCard = page
    .locator(".saved-search-list article")
    .filter({ hasText: "Methods follow-up" });
  await expect(savedCard.getByText("Methods follow-up", { exact: true })).toBeVisible();
  await expect(savedCard.getByText("methodology", { exact: true })).toBeVisible();

  await savedCard.getByRole("button", { name: "Run" }).click();
  await expect(page.getByRole("heading", { name: "Methods follow-up" })).toBeVisible();
  await expect(page.getByText("We started the methodology program after the second interview round.")).toBeVisible();

  const runResults = page.locator(".research-run-results");
  await runResults.getByRole("button", { name: "Open verified evidence" }).click();
  await expect(page.getByText("Current verified canonical generation")).toBeVisible();
  await page.getByRole("complementary", { name: "Evidence reader" }).getByRole("button", { name: "Close" }).click();

  await savedCard.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByLabel("Delete saved search Methods follow-up")).toContainText(
    "Notes, transcripts, and recordings are not part of this operation",
  );
  await savedCard.getByRole("button", { name: "Delete saved search" }).click();
  await expect(page.getByText("Methods follow-up", { exact: true })).toHaveCount(0);
  await expect(
    page.getByText("Saved search deleted. Notes and transcripts were not deleted."),
  ).toBeVisible();

  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
