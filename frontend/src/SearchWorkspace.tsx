import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import type {
  DesktopClient,
  WorkspaceDiscoveryReport,
  WorkspaceEvidenceResult,
} from "./api/desktop";
import type {
  TranscriptGenerationRef,
  TranscriptToolsClient,
} from "./api/transcriptTools";
import { WorkspaceHeader, type Theme } from "./components/WorkspaceHeader";
import { EvidenceReader } from "./EvidenceReader";
import { formatEvidenceTime } from "./format";
import { TranscriptToolsPanel } from "./TranscriptToolsPanel";
import "./search.css";

interface SearchWorkspaceProps {
  client: DesktopClient;
  transcriptTools: TranscriptToolsClient;
  theme: Theme;
  onThemeChange: (theme: Theme) => void;
}

export function SearchWorkspace({
  client,
  transcriptTools,
  theme,
  onThemeChange,
}: SearchWorkspaceProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [report, setReport] = useState<WorkspaceDiscoveryReport | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<WorkspaceEvidenceResult | null>(null);
  const [selectedTools, setSelectedTools] = useState<TranscriptGenerationRef | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState("Search transcripts and your research.");

  useEffect(() => {
    function focusSearch(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        inputRef.current?.focus();
      }
    }
    window.addEventListener("keydown", focusSearch);
    return () => window.removeEventListener("keydown", focusSearch);
  }, []);

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = query.trim();
    if (!text) {
      setError("Enter something to search for.");
      inputRef.current?.focus();
      return;
    }
    setBusy(true);
    setError(null);
    setSelectedEvidence(null);
    setSelectedTools(null);
    try {
      const next = await client.discoverWorkspace(text);
      setReport(next);
      setStatus(`${next.total_count} result${next.total_count === 1 ? "" : "s"}.`);
    } catch (caught) {
      setReport(null);
      setError(
        caught instanceof Error ? caught.message : "EchoFlow could not search your library.",
      );
    } finally {
      setBusy(false);
    }
  }

  function openEvidence(item: WorkspaceEvidenceResult) {
    setSelectedTools(null);
    setSelectedEvidence(item);
    setStatus(`Opened ${item.document_id} at ${formatEvidenceTime(item.seek_seconds)}.`);
  }

  function openTools(item: WorkspaceEvidenceResult) {
    setSelectedEvidence(null);
    setSelectedTools({
      document_id: item.document_id,
      canonical_sha256: item.canonical_sha256,
    });
    setStatus(`Opening transcript tools for ${item.document_id}.`);
  }

  async function createNote(body: string) {
    if (selectedEvidence === null) {
      throw new Error("That transcript passage is no longer open.");
    }
    const created = await client.createResearchNote(selectedEvidence, body);
    setStatus(`Note saved to ${created.document_id}.`);
  }

  return (
    <>
      <WorkspaceHeader
        eyebrow="Library"
        title="Search your library."
        theme={theme}
        onThemeChange={onThemeChange}
      />

      <section className="search-intro" aria-labelledby="search-title">
        <div>
          <p className="section-kicker">Search</p>
          <h2 id="search-title">Search transcripts, notes, tags, and collections.</h2>
        </div>
        <p>Open a transcript result to see the exact passage, manage speakers, or publish a derived copy.</p>
      </section>

      <form className="global-search" role="search" onSubmit={(event) => void search(event)}>
        <label htmlFor="workspace-search" className="search-label">
          Search EchoFlow
        </label>
        <div className="search-control">
          <span aria-hidden="true" className="search-glyph">⌕</span>
          <input
            id="workspace-search"
            ref={inputRef}
            type="search"
            value={query}
            maxLength={4096}
            autoComplete="off"
            placeholder="Search transcripts, notes, tags, collections…"
            onChange={(event) => setQuery(event.target.value)}
          />
          <kbd>Ctrl K</kbd>
          <button type="submit" disabled={busy}>
            {busy ? "Searching…" : "Search"}
          </button>
        </div>
      </form>

      <p className="search-status" role="status">{status}</p>
      {error && <p className="error-banner search-error" role="alert">{error}</p>}

      {selectedEvidence && (
        <EvidenceReader
          evidence={selectedEvidence}
          onClose={() => setSelectedEvidence(null)}
          onCreateNote={createNote}
        />
      )}

      {selectedTools && (
        <TranscriptToolsPanel
          client={transcriptTools}
          generation={selectedTools}
          onClose={() => setSelectedTools(null)}
        />
      )}

      {report && (
        <div className="result-groups" aria-label={`Search results for ${report.query}`}>
          <section className="result-group" aria-labelledby="evidence-results">
            <div className="result-group-heading">
              <div>
                <p className="mini-label">Transcripts</p>
                <h2 id="evidence-results">Transcript passages</h2>
              </div>
              <span className="result-count" aria-label={`${report.evidence.length} transcript results`}>
                {report.evidence.length}
              </span>
            </div>
            {report.evidence.length === 0 ? (
              <p className="empty-result">No transcript passages matched.</p>
            ) : (
              <div className="result-list">
                {report.evidence.map((item) => (
                  <article className="evidence-result" key={`${item.document_id}:${item.segment_ids.join(",")}`}>
                    <div className="result-meta">
                      <span>{item.document_id}</span>
                      <time dateTime={`PT${item.seek_seconds}S`}>{formatEvidenceTime(item.seek_seconds)}</time>
                      <span>{item.languages.join(", ") || "language unknown"}</span>
                    </div>
                    <p className="result-text">{item.text}</p>
                    <div className="evidence-coordinate" data-seek-seconds={item.seek_seconds}>
                      <strong>Transcript location</strong>
                      <span>
                        {formatEvidenceTime(item.seek_seconds)} · {item.segment_ids.length} segment{item.segment_ids.length === 1 ? "" : "s"}
                      </span>
                    </div>
                    <div className="result-pills" aria-label="Transcript metadata">
                      {item.speakers.map((speaker) => (
                        <span key={speaker.speaker_ref}>
                          {speaker.display_label ?? speaker.speaker_ref}
                          {speaker.display_label ? ` · ${speaker.speaker_ref}` : ""}
                        </span>
                      ))}
                      {item.note_count > 0 && <span>{item.note_count} note{item.note_count === 1 ? "" : "s"}</span>}
                      {item.tags.map((tag) => <span key={`tag:${tag}`}>#{tag}</span>)}
                    </div>
                    <div className="result-actions">
                      <button
                        type="button"
                        className="open-evidence-button"
                        aria-label={`Open transcript passage from ${item.document_id} at ${formatEvidenceTime(item.seek_seconds)}`}
                        onClick={() => openEvidence(item)}
                      >
                        Open transcript passage
                      </button>
                      <button
                        type="button"
                        className="secondary-action"
                        aria-label={`Open transcript tools for ${item.document_id}`}
                        onClick={() => openTools(item)}
                      >
                        Transcript tools
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="result-group" aria-labelledby="note-results">
            <div className="result-group-heading">
              <div>
                <p className="mini-label">Research</p>
                <h2 id="note-results">Notes</h2>
              </div>
              <span className="result-count" aria-label={`${report.notes.length} note results`}>
                {report.notes.length}
              </span>
            </div>
            {report.notes.length === 0 ? (
              <p className="empty-result">No notes matched.</p>
            ) : (
              <div className="result-list">
                {report.notes.map((item) => (
                  <article className="note-result" key={item.note_id}>
                    <div className="result-meta">
                      <span>{item.document_id}</span>
                      <time dateTime={`PT${item.start_seconds}S`}>{formatEvidenceTime(item.start_seconds)}</time>
                      <span>{item.current ? "current transcript" : "earlier transcript version"}</span>
                    </div>
                    <p className="result-text">{item.body}</p>
                    <div className="result-pills">
                      {item.tags.map((tag) => <span key={`note-tag:${tag}`}>#{tag}</span>)}
                      {item.collections.map((collection) => <span key={`note-collection:${collection}`}>{collection}</span>)}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>

          <div className="named-result-grid">
            <section className="result-group compact-group" aria-labelledby="tag-results">
              <div className="result-group-heading">
                <h2 id="tag-results">Tags</h2>
                <span className="result-count" aria-label={`${report.tags.length} tag results`}>{report.tags.length}</span>
              </div>
              <div className="named-results">
                {report.tags.length === 0 ? <p className="empty-result">No tags matched.</p> : report.tags.map((item) => <span key={item.tag_id}>#{item.name}</span>)}
              </div>
            </section>
            <section className="result-group compact-group" aria-labelledby="collection-results">
              <div className="result-group-heading">
                <h2 id="collection-results">Collections</h2>
                <span className="result-count" aria-label={`${report.collections.length} collection results`}>{report.collections.length}</span>
              </div>
              <div className="named-results">
                {report.collections.length === 0 ? <p className="empty-result">No collections matched.</p> : report.collections.map((item) => <span key={item.collection_id}>{item.name}</span>)}
              </div>
            </section>
          </div>
        </div>
      )}
    </>
  );
}
