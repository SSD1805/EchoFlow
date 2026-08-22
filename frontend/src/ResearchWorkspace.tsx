import { useCallback, useEffect, useState, type FormEvent } from "react";

import type {
  DesktopClient,
  ResearchNoteResult,
  ResearchOverview,
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
  const [mutationMessage, setMutationMessage] = useState<string | null>(null);
  const [reader, setReader] = useState<ReaderState | null>(null);

  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  const [deleteNoteId, setDeleteNoteId] = useState<string | null>(null);
  const [mutatingNoteId, setMutatingNoteId] = useState<string | null>(null);
  const [openingNoteId, setOpeningNoteId] = useState<string | null>(null);
  const [draftBody, setDraftBody] = useState("");
  const [draftTags, setDraftTags] = useState("");
  const [draftCollections, setDraftCollections] = useState("");

  const [activeTags, setActiveTags] = useState<string[]>([]);
  const [activeCollections, setActiveCollections] = useState<string[]>([]);
  const [filteredNotes, setFilteredNotes] = useState<ResearchNoteResult[] | null>(null);
  const [filterBusy, setFilterBusy] = useState(false);

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
          : "Scholion could not open your research.",
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
        if (announce) setMutationMessage("Showing all notes.");
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
          : "Scholion could not apply those filters.",
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
    setMutationMessage("Notes, tags, and collections reloaded.");
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
      setMutationMessage("Note saved. Its transcript passage is unchanged.");
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Scholion could not update that note.",
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
      setMutationMessage("Note deleted. The transcript was not deleted.");
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Scholion could not delete that note.",
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
        resultLabel: "Transcript passage",
      });
      setMutationMessage(
        opened.current
          ? "Opened the transcript passage cited by this note."
          : "Opened the exact earlier transcript version cited by this note.",
      );
    } catch (caught) {
      setReader(null);
      setError(
        caught instanceof Error
          ? caught.message
          : "Scholion could not open the transcript passage cited by that note.",
      );
    } finally {
      setOpeningNoteId(null);
    }
  }

  async function createNoteFromReader(body: string) {
    if (!reader || reader.generationState !== "current") {
      throw new Error("New notes require the current transcript version.");
    }
    await client.createResearchNote(reader.evidence, body);
    await loadOverview();
    await refreshActiveFilters();
  }

  return (
    <>
      <WorkspaceHeader
        eyebrow="Research"
        title="Research"
        theme={theme}
        onThemeChange={onThemeChange}
      />

      <section className="research-intro" aria-labelledby="research-title">
        <div>
          <p className="section-kicker">Notes and labels</p>
          <h2 id="research-title">Keep your notes connected to the transcript.</h2>
        </div>
        <div className="research-intro-copy">
          <p>
            Browse and edit notes, filter them by tag or collection, and reopen the exact
            transcript passage each note points to. Reloading here updates research data;
            it does not scan your recording folders.
          </p>
          <button
            className="research-refresh"
            type="button"
            disabled={busy || filterBusy || mutatingNoteId !== null}
            onClick={() => void refreshResearch()}
          >
            {busy || filterBusy ? "Reloading…" : "Reload notes"}
          </button>
        </div>
      </section>

      <p className="research-status" role="status">
        {busy
          ? "Opening your research…"
          : overview
            ? `${overview.notes.length} notes · ${overview.tags.length} tags · ${overview.collections.length} collections`
            : "Research could not be opened."}
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

      {overview && (
        <div className="research-layout">
          <section className="research-panel research-notes" aria-labelledby="research-notes">
            <div className="research-panel-heading">
              <div>
                <p className="mini-label">Your notes</p>
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
                  : "No notes yet."}
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
                          {note.current ? "Current transcript" : "Earlier transcript version"}
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
                            Editing changes your note and labels. The transcript passage it
                            points to stays the same.
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
                              {opening ? "Opening…" : "Open transcript passage"}
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
                            Delete this note? This does not delete the transcript or original
                            recording.
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
            <section className="research-panel" aria-labelledby="research-labels">
              <div className="research-panel-heading">
                <div>
                  <p className="mini-label">Organize</p>
                  <h2 id="research-labels">Labels</h2>
                </div>
              </div>
              <p className="research-filter-explainer">
                Select more than one label to show notes that match every selected tag and collection.
              </p>
              <div className="label-section">
                <h3>Tags</h3>
                <div
                  className="research-pills research-label-buttons"
                  role="group"
                  aria-label="Research tags"
                >
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
