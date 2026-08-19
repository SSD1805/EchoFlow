import { useCallback, useEffect, useState } from "react";

import type { DesktopClient, ResearchOverview } from "./api/desktop";
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

export function ResearchWorkspace({
  client,
  theme,
  onThemeChange,
}: ResearchWorkspaceProps) {
  const [overview, setOverview] = useState<ResearchOverview | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
            This view reads authoritative notes, tags, collections, and saved-search intent
            from the local research workspace. Rebuildable search machinery is not the
            source of truth here.
          </p>
          <button
            className="research-refresh"
            type="button"
            disabled={busy}
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
                {overview.notes.map((note) => (
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
                    <p className="research-note-body">{note.body}</p>
                    <div className="research-note-footer">
                      <div className="research-pills" aria-label="Research labels">
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
                  </article>
                ))}
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
