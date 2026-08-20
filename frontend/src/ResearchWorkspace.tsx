import { useCallback, useEffect, useState, type FormEvent } from "react";

import type {
  DesktopClient,
  ResearchNoteResult,
  ResearchOverview,
} from "./api/desktop";
import { WorkspaceHeader, type Theme } from "./components/WorkspaceHeader";
import { formatEvidenceTime } from "./format";
import "./research.css";

interface ResearchWorkspaceProps {
  client: DesktopClient;
  theme: Theme;
  onThemeChange: (theme: Theme) => void;
}

function formatUpdatedAt(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function parseLabels(value: string): string[] {
  const labels = new Map<string, string>();
  value.split(",").forEach((raw) => {
    const label = raw.trim();
    if (label) labels.set(label.toLocaleLowerCase(), label);
  });
  return [...labels.values()];
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
  const [draftBody, setDraftBody] = useState("");
  const [draftTags, setDraftTags] = useState("");
  const [draftCollections, setDraftCollections] = useState("");
  const [mutationMessage, setMutationMessage] = useState<string | null>(null);

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
      setMutationMessage("Note deleted. Transcript evidence was not deleted.");
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "EchoFlow could not delete that note.",
      );
    } finally {
      setMutatingNoteId(null);
    }
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
            Browse and edit authoritative notes, tags, and collections beside saved-search
            intent. Rebuildable search machinery is not the source of truth here.
          </p>
          <button
            className="research-refresh"
            type="button"
            disabled={busy || mutatingNoteId !== null}
            onClick={() => void loadOverview()}
          >
            {busy ? "Refreshing…" : "Refresh research"}
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

      {overview && (
        <div className="research-layout">
          <section className="research-panel research-notes" aria-labelledby="research-notes">
            <div className="research-panel-heading">
              <div>
                <p className="mini-label">Authoritative annotations</p>
                <h2 id="research-notes">Notes</h2>
              </div>
              <span className="research-count">{overview.notes.length}</span>
            </div>

            {overview.notes.length === 0 ? (
              <p className="research-empty">No research notes yet.</p>
            ) : (
              <div className="research-note-list">
                {overview.notes.map((note) => {
                  const editing = editingNoteId === note.note_id;
                  const confirmingDelete = deleteNoteId === note.note_id;
                  const mutating = mutatingNoteId === note.note_id;
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
                              className="research-pills"
                              role="group"
                              aria-label="Research labels"
                            >
                              {note.tags.map((tag) => (
                                <span key={`${note.note_id}:tag:${tag}`}>#{tag}</span>
                              ))}
                              {note.collections.map((collection) => (
                                <span key={`${note.note_id}:collection:${collection}`}>
                                  {collection}
                                </span>
                              ))}
                            </div>
                            <time dateTime={note.updated_at} className="research-updated">
                              Updated {formatUpdatedAt(note.updated_at)}
                            </time>
                          </div>
                          <div className="research-note-actions">
                            <button
                              type="button"
                              disabled={mutatingNoteId !== null}
                              onClick={() => beginEdit(note)}
                            >
                              Edit note
                            </button>
                            <button
                              className="research-action-danger"
                              type="button"
                              disabled={mutatingNoteId !== null}
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
                        <div className="research-delete-confirm" role="group" aria-label="Delete note confirmation">
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
              {overview.saved_searches.length === 0 ? (
                <p className="research-empty">No saved searches yet.</p>
              ) : (
                <div className="saved-search-list">
                  {overview.saved_searches.map((saved) => (
                    <article key={saved.saved_search_id}>
                      <div className="saved-search-title-row">
                        <strong>{saved.name}</strong>
                        <span>{saved.retrieval_mode}</span>
                      </div>
                      {saved.description && <p>{saved.description}</p>}
                      <code>{saved.query_text}</code>
                    </article>
                  ))}
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
              <div className="label-section">
                <h3>Tags</h3>
                <div className="research-pills">
                  {overview.tags.length === 0 ? (
                    <span className="research-empty-inline">None yet</span>
                  ) : (
                    overview.tags.map((tag) => <span key={tag.tag_id}>#{tag.name}</span>)
                  )}
                </div>
              </div>
              <div className="label-section">
                <h3>Collections</h3>
                <div className="research-pills collection-pills">
                  {overview.collections.length === 0 ? (
                    <span className="research-empty-inline">None yet</span>
                  ) : (
                    overview.collections.map((collection) => (
                      <span key={collection.collection_id}>{collection.name}</span>
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
