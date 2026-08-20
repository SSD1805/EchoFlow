import { useCallback, useEffect, useState, type FormEvent } from "react";

import type {
  DesktopClient,
  ResearchNoteResult,
  ResearchOverview,
  ResearchSavedSearchResult,
  SavedSearchRunResult,
  WorkspaceEvidenceResult,
} from "./api/desktop";
import { WorkspaceHeader, type Theme } from "./components/WorkspaceHeader";
import { EvidenceReader } from "./EvidenceReader";
import { formatEvidenceTime } from "./format";
import "./research.css";
import "./research-label-navigation.css";

interface ResearchWorkspaceProps {
  client: DesktopClient;
  theme: Theme;
  onThemeChange: (theme: Theme) => void;
}

interface ReaderState {
  evidence: WorkspaceEvidenceResult;
  generationState: "current" | "older";
  resultLabel: string;
}

function formatUpdatedAt(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function normalizeLabels(values: string[]): string[] {
  const labels = new Map<string, string>();
  values.forEach((raw) => {
    const label = raw.trim();
    if (label) labels.set(label.toLocaleLowerCase(), label);
  });
  return [...labels.values()].sort((left, right) => left.localeCompare(right));
}

function parseLabels(value: string): string[] {
  return normalizeLabels(value.split(","));
}

function containsLabel(values: string[], label: string): boolean {
  const target = label.toLocaleLowerCase();
  return values.some((value) => value.toLocaleLowerCase() === target);
}

function toggleLabel(values: string[], label: string): string[] {
  if (containsLabel(values, label)) {
    const target = label.toLocaleLowerCase();
    return values.filter((value) => value.toLocaleLowerCase() !== target);
  }
  return normalizeLabels([...values, label]);
}

export function ResearchWorkspace({
  client,
  theme,
  onThemeChange,
}: ResearchWorkspaceProps) {
  const [overview, setOverview] = useState<ResearchOverview | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  const [deleteNoteId, setDeleteNoteId] = useState<string | null>(null);
  const [mutatingNoteId, setMutatingNoteId] = useState<string | null>(null);
  const [openingNoteId, setOpeningNoteId] = useState<string | null>(null);
  const [draftBody, setDraftBody] = useState("");
  const [draftTags, setDraftTags] = useState("");
  const [draftCollections, setDraftCollections] = useState("");
  const [mutationMessage, setMutationMessage] = useState<string | null>(null);
  const [reader, setReader] = useState<ReaderState | null>(null);

  const [activeTags, setActiveTags] = useState<string[]>([]);
  const [activeCollections, setActiveCollections] = useState<string[]>([]);
  const [filteredNotes, setFilteredNotes] = useState<ResearchNoteResult[] | null>(null);
  const [filterBusy, setFilterBusy] = useState(false);

  const [savedName, setSavedName] = useState("");
  const [savedQuery, setSavedQuery] = useState("");
  const [savedDescription, setSavedDescription] = useState("");
  const [editingSavedId, setEditingSavedId] = useState<string | null>(null);
  const [deleteSavedId, setDeleteSavedId] = useState<string | null>(null);
  const [mutatingSavedId, setMutatingSavedId] = useState<string | null>(null);
  const [savedDraftName, setSavedDraftName] = useState("");
  const [savedDraftDescription, setSavedDraftDescription] = useState("");
  const [savedRun, setSavedRun] = useState<SavedSearchRunResult | null>(null);

  const hasActiveFilters = activeTags.length > 0 || activeCollections.length > 0;
  const visibleNotes = overview
    ? hasActiveFilters
      ? (filteredNotes ?? [])
      : overview.notes
    : [];

  const loadOverview = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setOverview(await client.researchOverview());
    } catch (caught) {
      setOverview(null);
      setError(
        caught instanceof Error
          ? caught.message
          : "EchoFlow could not open the local research workspace.",
      );
    } finally {
      setBusy(false);
    }
  }, [client]);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  async function applyResearchFilters(
    tags: string[],
    collections: string[],
    announce = true,
  ) {
    const nextTags = normalizeLabels(tags);
    const nextCollections = normalizeLabels(collections);
    setFilterBusy(true);
    setError(null);
    if (announce) setMutationMessage(null);
    try {
      if (nextTags.length === 0 && nextCollections.length === 0) {
        setActiveTags([]);
        setActiveCollections([]);
        setFilteredNotes(null);
        if (announce) setMutationMessage("Showing all research notes.");
        return;
      }
      const result = await client.filterResearchNotes(nextTags, nextCollections);
      setActiveTags(result.tags);
      setActiveCollections(result.collections);
      setFilteredNotes(result.notes);
      if (announce) {
        const noun = result.notes.length === 1 ? "note" : "notes";
        setMutationMessage(
          `Showing ${result.notes.length} ${noun} matching every selected label.`,
        );
      }
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "EchoFlow could not apply those research filters.",
      );
    } finally {
      setFilterBusy(false);
    }
  }

  async function refreshActiveFilters() {
    if (hasActiveFilters) {
      await applyResearchFilters(activeTags, activeCollections, false);
    }
  }

  async function refreshResearch() {
    await loadOverview();
    await refreshActiveFilters();
  }

  function beginEdit(note: ResearchNoteResult) {
    setEditingNoteId(note.note_id);
    setDeleteNoteId(null);
    setDraftBody(note.body);
    setDraftTags(note.tags.join(", "));
    setDraftCollections(note.collections.join(", "));
    setMutationMessage(null);
    setError(null);
  }

  function cancelEdit() {
    setEditingNoteId(null);
    setDraftBody("");
    setDraftTags("");
    setDraftCollections("");
  }

  async function saveEdit(event: FormEvent, note: ResearchNoteResult) {
    event.preventDefault();
    setMutatingNoteId(note.note_id);
    setMutationMessage(null);
    setError(null);
    try {
      await client.updateResearchNote(note, {
        body: draftBody,
        tags: parseLabels(draftTags),
        collections: parseLabels(draftCollections),
      });
      cancelEdit();
      await loadOverview();
      await refreshActiveFilters();
      setMutationMessage("Note saved. Its verified evidence anchor is unchanged.");
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "EchoFlow could not update that note.",
      );
    } finally {
      setMutatingNoteId(null);
    }
  }

  async function deleteNote(note: ResearchNoteResult) {
    setMutatingNoteId(note.note_id);
    setMutationMessage(null);
    setError(null);
    try {
      await client.deleteResearchNote(note);
      setDeleteNoteId(null);
      if (editingNoteId === note.note_id) cancelEdit();
      await loadOverview();
      await refreshActiveFilters();
      setMutationMessage("Note deleted. Transcript evidence was not deleted.");
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "EchoFlow could not delete that note.",
      );
    } finally {
      setMutatingNoteId(null);
    }
  }

  async function openNoteEvidence(note: ResearchNoteResult) {
    setOpeningNoteId(note.note_id);
    setMutationMessage(null);
    setError(null);
    try {
      const opened = await client.openResearchNoteEvidence(note);
      setReader({
        evidence: opened.evidence,
        generationState: opened.current ? "current" : "older",
        resultLabel: "Anchored evidence",
      });
      setMutationMessage(
        opened.current
          ? "Opened this note’s current verified evidence."
          : "Opened the exact older evidence generation cited by this note. Nothing was rebound.",
      );
    } catch (caught) {
      setReader(null);
      setError(
        caught instanceof Error
          ? caught.message
          : "EchoFlow could not verify the evidence cited by that note.",
      );
    } finally {
      setOpeningNoteId(null);
    }
  }

  async function createNoteFromReader(body: string) {
    if (!reader || reader.generationState !== "current") {
      throw new Error("New notes require current verified evidence.");
    }
    await client.createResearchNote(reader.evidence, body);
    await loadOverview();
    await refreshActiveFilters();
  }

  async function createSavedSearch(event: FormEvent) {
    event.preventDefault();
    setMutatingSavedId("new");
    setMutationMessage(null);
    setError(null);
    try {
      const created = await client.createSavedSearch(
        savedName,
        savedQuery,
        savedDescription || null,
      );
      setSavedName("");
      setSavedQuery("");
      setSavedDescription("");
      await loadOverview();
      setMutationMessage(`Saved “${created.name}” as durable search intent.`);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "EchoFlow could not save that research question.",
      );
    } finally {
      setMutatingSavedId(null);
    }
  }

  function beginSavedEdit(saved: ResearchSavedSearchResult) {
    setEditingSavedId(saved.saved_search_id);
    setDeleteSavedId(null);
    setSavedDraftName(saved.name);
    setSavedDraftDescription(saved.description ?? "");
    setMutationMessage(null);
    setError(null);
  }

  async function saveSavedEdit(event: FormEvent, saved: ResearchSavedSearchResult) {
    event.preventDefault();
    setMutatingSavedId(saved.saved_search_id);
    setMutationMessage(null);
    setError(null);
    try {
      const updated = await client.updateSavedSearch(
        saved,
        savedDraftName,
        savedDraftDescription || null,
      );
      setEditingSavedId(null);
      await loadOverview();
      setMutationMessage(`Renamed saved search to “${updated.name}”. Its typed query is unchanged.`);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "EchoFlow could not update that saved search.",
      );
    } finally {
      setMutatingSavedId(null);
    }
  }

  async function deleteSavedSearch(saved: ResearchSavedSearchResult) {
    setMutatingSavedId(saved.saved_search_id);
    setMutationMessage(null);
    setError(null);
    try {
      await client.deleteSavedSearch(saved);
      setDeleteSavedId(null);
      if (editingSavedId === saved.saved_search_id) setEditingSavedId(null);
      if (savedRun?.saved_search.saved_search_id === saved.saved_search_id) setSavedRun(null);
      await loadOverview();
      setMutationMessage("Saved search deleted. Transcript evidence and research notes were untouched.");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "EchoFlow could not delete that saved search.",
      );
    } finally {
      setMutatingSavedId(null);
    }
  }

  async function runSavedSearch(saved: ResearchSavedSearchResult) {
    setMutatingSavedId(saved.saved_search_id);
    setMutationMessage(null);
    setError(null);
    try {
      const result = await client.runSavedSearch(saved);
      setSavedRun(result);
      setMutationMessage(
        `Ran “${result.saved_search.name}” against current evidence and research relationships.`,
      );
    } catch (caught) {
      setSavedRun(null);
      setError(
        caught instanceof Error ? caught.message : "EchoFlow could not run that saved search.",
      );
    } finally {
      setMutatingSavedId(null);
    }
  }

  function openSavedEvidence(evidence: WorkspaceEvidenceResult) {
    setReader({ evidence, generationState: "current", resultLabel: "Saved-search result" });
    setError(null);
  }

  return (
    <>
      <WorkspaceHeader
        eyebrow="Research"
        title="Your research layer."
        theme={theme}
        onThemeChange={onThemeChange}
      />

      <section className="research-intro" aria-labelledby="research-title">
        <div>
          <p className="section-kicker">03 · Human knowledge stays human knowledge</p>
          <h2 id="research-title">Notes beside evidence, not trapped inside an index.</h2>
        </div>
        <div className="research-intro-copy">
          <p>
            Browse and edit authoritative research, reopen the exact evidence it cites, and
            replay durable search intent against what exists now. The webview never decides
            which canonical generation counts as evidence.
          </p>
          <button
            className="research-refresh"
            type="button"
            disabled={
              busy ||
              filterBusy ||
              mutatingNoteId !== null ||
              mutatingSavedId !== null
            }
            onClick={() => void refreshResearch()}
          >
            {busy || filterBusy ? "Refreshing…" : "Refresh research"}
          </button>
        </div>
      </section>

      <p className="research-status" role="status">
        {busy
          ? "Reading local research state…"
          : overview
            ? `${overview.notes.length} notes · ${overview.tags.length} tags · ${overview.collections.length} collections · ${overview.saved_searches.length} saved searches`
            : "Research state is unavailable."}
      </p>

      {mutationMessage && (
        <p className="research-mutation-status" aria-live="polite">
          {mutationMessage}
        </p>
      )}

      {error && (
        <p className="error-banner research-error" role="alert">
          {error}
        </p>
      )}

      {reader && (
        <EvidenceReader
          evidence={reader.evidence}
          generationState={reader.generationState}
          resultLabel={reader.resultLabel}
          onClose={() => setReader(null)}
          onCreateNote={
            reader.generationState === "current" ? createNoteFromReader : undefined
          }
        />
      )}

      {savedRun && (
        <section className="research-run-results" aria-labelledby="saved-run-title">
          <div className="research-panel-heading">
            <div>
              <p className="mini-label">Current replay</p>
              <h2 id="saved-run-title">{savedRun.saved_search.name}</h2>
              <p>
                Query: <code>{savedRun.query}</code>
              </p>
            </div>
            <span className="research-count">{savedRun.evidence.length}</span>
          </div>
          {savedRun.evidence.length === 0 ? (
            <p className="research-empty">No current evidence matches this saved intent.</p>
          ) : (
            <div className="research-run-list">
              {savedRun.evidence.map((evidence) => (
                <article
                  key={`${evidence.document_id}:${evidence.canonical_sha256}:${evidence.segment_ids.join(":")}`}
                >
                  <div>
                    <strong>{evidence.document_id}</strong>
                    <span>{formatEvidenceTime(evidence.start_seconds)}</span>
                  </div>
                  <p>{evidence.text}</p>
                  <button
                    type="button"
                    className="open-evidence-button"
                    onClick={() => openSavedEvidence(evidence)}
                  >
                    Open verified evidence
                  </button>
                </article>
              ))}
            </div>
          )}
        </section>
      )}

      {overview && (
        <div className="research-layout">
          <section className="research-panel research-notes" aria-labelledby="research-notes">
            <div className="research-panel-heading">
              <div>
                <p className="mini-label">Authoritative annotations</p>
                <h2 id="research-notes">Notes</h2>
              </div>
              <span className="research-count">{visibleNotes.length}</span>
            </div>

            {hasActiveFilters && (
              <div
                className="research-active-filters"
                role="region"
                aria-label="Active research filters"
              >
                <div className="research-active-filter-heading">
                  <div>
                    <strong>Active filters</strong>
                    <span>Every selected label must match the same note.</span>
                  </div>
                  <button
                    type="button"
                    disabled={filterBusy}
                    onClick={() => void applyResearchFilters([], [])}
                  >
                    Clear filters
                  </button>
                </div>
                <div className="research-active-filter-pills">
                  {activeTags.map((tag) => (
                    <button
                      key={`active-tag:${tag}`}
                      type="button"
                      aria-label={`Remove tag ${tag}`}
                      disabled={filterBusy}
                      onClick={() =>
                        void applyResearchFilters(
                          toggleLabel(activeTags, tag),
                          activeCollections,
                        )
                      }
                    >
                      #{tag} <span aria-hidden="true">×</span>
                    </button>
                  ))}
                  {activeCollections.map((collection) => (
                    <button
                      key={`active-collection:${collection}`}
                      type="button"
                      aria-label={`Remove collection ${collection}`}
                      disabled={filterBusy}
                      onClick={() =>
                        void applyResearchFilters(
                          activeTags,
                          toggleLabel(activeCollections, collection),
                        )
                      }
                    >
                      {collection} <span aria-hidden="true">×</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {visibleNotes.length === 0 ? (
              <p className="research-empty">
                {hasActiveFilters
                  ? "No notes match every selected label."
                  : "No research notes yet."}
              </p>
            ) : (
              <div className="research-note-list">
                {visibleNotes.map((note) => {
                  const editing = editingNoteId === note.note_id;
                  const confirmingDelete = deleteNoteId === note.note_id;
                  const mutating = mutatingNoteId === note.note_id;
                  const opening = openingNoteId === note.note_id;
                  return (
                    <article className="research-note-card" key={note.note_id}>
                      <div className="research-note-meta">
                        <span>{note.document_id}</span>
                        <time dateTime={`PT${note.start_seconds}S`}>
                          {formatEvidenceTime(note.start_seconds)}
                        </time>
                        <span
                          className={
                            note.current
                              ? "evidence-state evidence-state-current"
                              : "evidence-state evidence-state-older"
                          }
                        >
                          {note.current ? "Current evidence" : "Older evidence generation"}
                        </span>
                      </div>

                      {editing ? (
                        <form
                          className="research-note-editor"
                          onSubmit={(event) => void saveEdit(event, note)}
                        >
                          <label>
                            Note
                            <textarea
                              aria-label={`Note text for ${note.document_id}`}
                              value={draftBody}
                              maxLength={50_000}
                              rows={5}
                              disabled={mutating}
                              onChange={(event) => setDraftBody(event.target.value)}
                            />
                          </label>
                          <div className="research-editor-grid">
                            <label>
                              Tags
                              <input
                                aria-label={`Tags for ${note.document_id}`}
                                value={draftTags}
                                disabled={mutating}
                                onChange={(event) => setDraftTags(event.target.value)}
                                placeholder="methodology, follow-up"
                              />
                            </label>
                            <label>
                              Collections
                              <input
                                aria-label={`Collections for ${note.document_id}`}
                                value={draftCollections}
                                disabled={mutating}
                                onChange={(event) => setDraftCollections(event.target.value)}
                                placeholder="Chapter 3, Oral histories"
                              />
                            </label>
                          </div>
                          <p className="research-anchor-note">
                            Editing changes only your note and labels. The exact canonical
                            evidence generation and coordinates stay unchanged.
                          </p>
                          <div className="research-note-actions">
                            <button type="submit" disabled={mutating || !draftBody.trim()}>
                              {mutating ? "Saving…" : "Save note"}
                            </button>
                            <button type="button" disabled={mutating} onClick={cancelEdit}>
                              Cancel
                            </button>
                          </div>
                        </form>
                      ) : (
                        <>
                          <p className="research-note-body">{note.body}</p>
                          <div className="research-note-footer">
                            <div
                              className="research-pills research-label-buttons"
                              role="group"
                              aria-label={`Research labels for ${note.document_id}`}
                            >
                              {note.tags.map((tag) => (
                                <button
                                  key={`${note.note_id}:tag:${tag}`}
                                  type="button"
                                  aria-pressed={containsLabel(activeTags, tag)}
                                  disabled={filterBusy}
                                  onClick={() =>
                                    void applyResearchFilters(
                                      toggleLabel(activeTags, tag),
                                      activeCollections,
                                    )
                                  }
                                >
                                  #{tag}
                                </button>
                              ))}
                              {note.collections.map((collection) => (
                                <button
                                  key={`${note.note_id}:collection:${collection}`}
                                  type="button"
                                  aria-pressed={containsLabel(
                                    activeCollections,
                                    collection,
                                  )}
                                  disabled={filterBusy}
                                  onClick={() =>
                                    void applyResearchFilters(
                                      activeTags,
                                      toggleLabel(activeCollections, collection),
                                    )
                                  }
                                >
                                  {collection}
                                </button>
                              ))}
                            </div>
                            <time dateTime={note.updated_at} className="research-updated">
                              Updated {formatUpdatedAt(note.updated_at)}
                            </time>
                          </div>
                          <div className="research-note-actions">
                            <button
                              type="button"
                              disabled={mutatingNoteId !== null || openingNoteId !== null}
                              onClick={() => void openNoteEvidence(note)}
                            >
                              {opening ? "Verifying…" : "Open verified evidence"}
                            </button>
                            <button
                              type="button"
                              disabled={mutatingNoteId !== null || openingNoteId !== null}
                              onClick={() => beginEdit(note)}
                            >
                              Edit note
                            </button>
                            <button
                              className="research-action-danger"
                              type="button"
                              disabled={mutatingNoteId !== null || openingNoteId !== null}
                              onClick={() => {
                                setDeleteNoteId(note.note_id);
                                setMutationMessage(null);
                              }}
                            >
                              Delete note
                            </button>
                          </div>
                        </>
                      )}

                      {confirmingDelete && !editing && (
                        <div
                          className="research-delete-confirm"
                          role="group"
                          aria-label="Delete note confirmation"
                        >
                          <p>
                            Delete this human-authored note? Its canonical transcript and
                            original recording are not part of this operation.
                          </p>
                          <div className="research-note-actions">
                            <button
                              className="research-action-danger"
                              type="button"
                              disabled={mutating}
                              onClick={() => void deleteNote(note)}
                            >
                              {mutating ? "Deleting…" : "Delete note permanently"}
                            </button>
                            <button
                              type="button"
                              disabled={mutating}
                              onClick={() => setDeleteNoteId(null)}
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            )}
          </section>

          <aside className="research-side" aria-label="Research navigation">
            <section className="research-panel saved-searches" aria-labelledby="saved-searches">
              <div className="research-panel-heading">
                <div>
                  <p className="mini-label">Durable questions</p>
                  <h2 id="saved-searches">Saved searches</h2>
                </div>
                <span className="research-count">{overview.saved_searches.length}</span>
              </div>

              <form
                className="saved-search-create"
                onSubmit={(event) => void createSavedSearch(event)}
              >
                <label>
                  Name
                  <input
                    aria-label="Saved search name"
                    value={savedName}
                    maxLength={200}
                    disabled={mutatingSavedId !== null}
                    onChange={(event) => setSavedName(event.target.value)}
                  />
                </label>
                <label>
                  Query
                  <input
                    aria-label="Saved search query"
                    value={savedQuery}
                    maxLength={4096}
                    disabled={mutatingSavedId !== null}
                    onChange={(event) => setSavedQuery(event.target.value)}
                  />
                </label>
                <label>
                  Description <span>(optional)</span>
                  <textarea
                    aria-label="Saved search description"
                    value={savedDescription}
                    maxLength={4000}
                    rows={2}
                    disabled={mutatingSavedId !== null}
                    onChange={(event) => setSavedDescription(event.target.value)}
                  />
                </label>
                <p>
                  EchoFlow saves typed intent, not today’s result list. Running it later asks the
                  same question of current evidence and research relationships.
                </p>
                <button
                  type="submit"
                  disabled={
                    mutatingSavedId !== null || !savedName.trim() || !savedQuery.trim()
                  }
                >
                  {mutatingSavedId === "new" ? "Saving…" : "Save search"}
                </button>
              </form>

              {overview.saved_searches.length === 0 ? (
                <p className="research-empty">No saved searches yet.</p>
              ) : (
                <div className="saved-search-list">
                  {overview.saved_searches.map((saved) => {
                    const editing = editingSavedId === saved.saved_search_id;
                    const confirmingDelete = deleteSavedId === saved.saved_search_id;
                    const mutating = mutatingSavedId === saved.saved_search_id;
                    return (
                      <article key={saved.saved_search_id}>
                        {editing ? (
                          <form
                            className="saved-search-editor"
                            onSubmit={(event) => void saveSavedEdit(event, saved)}
                          >
                            <label>
                              Name
                              <input
                                aria-label={`Saved search name for ${saved.query_text}`}
                                value={savedDraftName}
                                maxLength={200}
                                disabled={mutating}
                                onChange={(event) => setSavedDraftName(event.target.value)}
                              />
                            </label>
                            <label>
                              Description
                              <textarea
                                aria-label={`Saved search description for ${saved.query_text}`}
                                value={savedDraftDescription}
                                maxLength={4000}
                                rows={2}
                                disabled={mutating}
                                onChange={(event) =>
                                  setSavedDraftDescription(event.target.value)
                                }
                              />
                            </label>
                            <p>
                              Rename edits display metadata only. The backend preserves the typed
                              query intent.
                            </p>
                            <div className="saved-search-actions">
                              <button type="submit" disabled={mutating || !savedDraftName.trim()}>
                                {mutating ? "Saving…" : "Save name"}
                              </button>
                              <button
                                type="button"
                                disabled={mutating}
                                onClick={() => setEditingSavedId(null)}
                              >
                                Cancel
                              </button>
                            </div>
                          </form>
                        ) : (
                          <>
                            <div className="saved-search-title-row">
                              <strong>{saved.name}</strong>
                              <span>{saved.retrieval_mode}</span>
                            </div>
                            {saved.description && <p>{saved.description}</p>}
                            <code>{saved.query_text}</code>
                            <div className="saved-search-actions">
                              <button
                                type="button"
                                disabled={mutatingSavedId !== null}
                                onClick={() => void runSavedSearch(saved)}
                              >
                                {mutating ? "Running…" : "Run"}
                              </button>
                              <button
                                type="button"
                                disabled={mutatingSavedId !== null}
                                onClick={() => beginSavedEdit(saved)}
                              >
                                Rename
                              </button>
                              <button
                                className="research-action-danger"
                                type="button"
                                disabled={mutatingSavedId !== null}
                                onClick={() => {
                                  setDeleteSavedId(saved.saved_search_id);
                                  setMutationMessage(null);
                                }}
                              >
                                Delete
                              </button>
                            </div>
                          </>
                        )}
                        {confirmingDelete && !editing && (
                          <div
                            className="research-delete-confirm"
                            role="group"
                            aria-label={`Delete saved search ${saved.name}`}
                          >
                            <p>
                              Delete this durable question? Notes, transcripts, and recordings are
                              not part of this operation.
                            </p>
                            <div className="saved-search-actions">
                              <button
                                className="research-action-danger"
                                type="button"
                                disabled={mutating}
                                onClick={() => void deleteSavedSearch(saved)}
                              >
                                {mutating ? "Deleting…" : "Delete saved search"}
                              </button>
                              <button
                                type="button"
                                disabled={mutating}
                                onClick={() => setDeleteSavedId(null)}
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        )}
                      </article>
                    );
                  })}
                </div>
              )}
            </section>

            <section className="research-panel" aria-labelledby="research-labels">
              <div className="research-panel-heading">
                <div>
                  <p className="mini-label">Current vocabulary</p>
                  <h2 id="research-labels">Labels</h2>
                </div>
              </div>
              <p className="research-filter-explainer">
                Select more than one label to narrow notes by every selected tag and collection.
              </p>
              <div className="label-section">
                <h3>Tags</h3>
                <div className="research-pills research-label-buttons" role="group" aria-label="Research tags">
                  {overview.tags.length === 0 ? (
                    <span className="research-empty-inline">None yet</span>
                  ) : (
                    overview.tags.map((tag) => (
                      <button
                        key={tag.tag_id}
                        type="button"
                        aria-pressed={containsLabel(activeTags, tag.name)}
                        disabled={filterBusy}
                        onClick={() =>
                          void applyResearchFilters(
                            toggleLabel(activeTags, tag.name),
                            activeCollections,
                          )
                        }
                      >
                        #{tag.name}
                      </button>
                    ))
                  )}
                </div>
              </div>
              <div className="label-section">
                <h3>Collections</h3>
                <div
                  className="research-pills collection-pills research-label-buttons"
                  role="group"
                  aria-label="Research collections"
                >
                  {overview.collections.length === 0 ? (
                    <span className="research-empty-inline">None yet</span>
                  ) : (
                    overview.collections.map((collection) => (
                      <button
                        key={collection.collection_id}
                        type="button"
                        aria-pressed={containsLabel(
                          activeCollections,
                          collection.name,
                        )}
                        disabled={filterBusy}
                        onClick={() =>
                          void applyResearchFilters(
                            activeTags,
                            toggleLabel(activeCollections, collection.name),
                          )
                        }
                      >
                        {collection.name}
                      </button>
                    ))
                  )}
                </div>
              </div>
            </section>
          </aside>
        </div>
      )}
    </>
  );
}
