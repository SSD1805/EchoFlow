import { useCallback, useEffect, useState, type FormEvent } from "react";

import type {
  DesktopClient,
  ResearchSavedSearchResult,
  ResearchSearchIntent,
  ResearchSearchResult,
  ResearchTypedSavedSearchResult,
  WorkspaceEvidenceResult,
} from "./api/desktop";
import { EvidenceReader } from "./EvidenceReader";
import { formatEvidenceTime } from "./format";
import "./research-search-controls.css";

interface ResearchSearchControlsPanelProps {
  client: DesktopClient;
  revision?: number;
  onResearchChanged?: () => void;
}

type SearchMatch = "any" | "all" | "phrase";

interface SearchDraft {
  queryText: string;
  match: SearchMatch;
  speakerRefs: string;
  languages: string;
  documentIds: string;
  sort: "relevance" | "timeline";
  limit: string;
  retrievalMode: "lexical" | "semantic" | "hybrid";
  contextSegments: string;
  tags: string;
  collections: string;
  noteText: string;
  withNotes: boolean;
}

const EMPTY_DRAFT: SearchDraft = {
  queryText: "",
  match: "any",
  speakerRefs: "",
  languages: "",
  documentIds: "",
  sort: "relevance",
  limit: "20",
  retrievalMode: "lexical",
  contextSegments: "1",
  tags: "",
  collections: "",
  noteText: "",
  withNotes: false,
};

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function matchFromIntent(intent: ResearchSearchIntent): SearchMatch {
  if (intent.phrase) return "phrase";
  return intent.operator;
}

function draftToIntent(draft: SearchDraft): ResearchSearchIntent {
  return {
    query_text: draft.queryText,
    phrase: draft.match === "phrase",
    operator: draft.match === "any" ? "any" : "all",
    speaker_refs: splitList(draft.speakerRefs),
    languages: splitList(draft.languages),
    document_ids: splitList(draft.documentIds),
    sort: draft.sort,
    limit: Number(draft.limit),
    retrieval_mode: draft.retrievalMode,
    context_segments: Number(draft.contextSegments),
    tags: splitList(draft.tags),
    collections: splitList(draft.collections),
    note_text: draft.noteText.trim() || null,
    with_notes: draft.withNotes,
  };
}

function intentToDraft(intent: ResearchSearchIntent): SearchDraft {
  return {
    queryText: intent.query_text,
    match: matchFromIntent(intent),
    speakerRefs: intent.speaker_refs.join(", "),
    languages: intent.languages.join(", "),
    documentIds: intent.document_ids.join(", "),
    sort: intent.sort,
    limit: String(intent.limit),
    retrievalMode: intent.retrieval_mode,
    contextSegments: String(intent.context_segments),
    tags: intent.tags.join(", "),
    collections: intent.collections.join(", "),
    noteText: intent.note_text ?? "",
    withNotes: intent.with_notes,
  };
}

function matchLabel(intent: ResearchSearchIntent): string {
  if (intent.phrase) return "Exact phrase";
  return intent.operator === "all" ? "All of these words" : "Any of these words";
}

function retrievalLabel(mode: string): string {
  if (mode === "semantic") return "Meaning";
  if (mode === "hybrid") return "Wording + meaning";
  return "Wording";
}

function IntentSummary({ intent }: { intent: ResearchSearchIntent }) {
  const chips = [
    `Match: ${matchLabel(intent)}`,
    `Search by: ${retrievalLabel(intent.retrieval_mode)}`,
    `Order: ${intent.sort === "timeline" ? "Time" : "Relevance"}`,
    `Results: ${intent.limit}`,
    `Context: ${intent.context_segments}`,
    ...intent.speaker_refs.map((value) => `Speaker: ${value}`),
    ...intent.languages.map((value) => `Language: ${value}`),
    ...intent.document_ids.map((value) => `Transcript: ${value}`),
    ...intent.tags.map((value) => `Tag: ${value}`),
    ...intent.collections.map((value) => `Collection: ${value}`),
    ...(intent.note_text ? [`Notes containing: ${intent.note_text}`] : []),
    ...(intent.with_notes ? ["Only results with notes"] : []),
  ];

  return (
    <div className="typed-search-intent" aria-label="Search details">
      <strong>Search details</strong>
      <code>{intent.query_text}</code>
      <div className="typed-search-pills">
        {chips.map((chip) => (
          <span key={chip}>{chip}</span>
        ))}
      </div>
    </div>
  );
}

export function ResearchSearchControlsPanel({
  client,
  revision = 0,
  onResearchChanged,
}: ResearchSearchControlsPanelProps) {
  const [draft, setDraft] = useState<SearchDraft>(EMPTY_DRAFT);
  const [result, setResult] = useState<ResearchSearchResult | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<WorkspaceEvidenceResult | null>(
    null,
  );
  const [savedSearches, setSavedSearches] = useState<ResearchSavedSearchResult[]>([]);
  const [editingSaved, setEditingSaved] = useState<ResearchTypedSavedSearchResult | null>(
    null,
  );
  const [savedName, setSavedName] = useState("");
  const [savedDescription, setSavedDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [savedBusy, setSavedBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState("Search transcript evidence and your research.");

  const loadSavedSearches = useCallback(async () => {
    const overview = await client.researchOverview();
    setSavedSearches(overview.saved_searches);
  }, [client]);

  useEffect(() => {
    void loadSavedSearches().catch((caught) => {
      setError(
        caught instanceof Error
          ? caught.message
          : "EchoFlow could not read your saved searches.",
      );
    });
  }, [loadSavedSearches, revision]);

  function updateDraft<K extends keyof SearchDraft>(key: K, value: SearchDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  async function executeSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setSelectedEvidence(null);
    try {
      const next = await client.executeResearchSearch(draftToIntent(draft));
      setResult(next);
      setDraft(intentToDraft(next.intent));
      setStatus(
        `${next.evidence.length} verified evidence result${next.evidence.length === 1 ? "" : "s"}.`,
      );
    } catch (caught) {
      setResult(null);
      setError(
        caught instanceof Error
          ? caught.message
          : "EchoFlow could not run that research search.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function createSavedIntent() {
    setSavedBusy(true);
    setError(null);
    try {
      const saved = await client.createTypedSavedSearch(
        savedName,
        savedDescription.trim() || null,
        draftToIntent(draft),
      );
      setEditingSaved(saved);
      setDraft(intentToDraft(saved.intent));
      setSavedName(saved.name);
      setSavedDescription(saved.description ?? "");
      await loadSavedSearches();
      onResearchChanged?.();
      setStatus(`Saved “${saved.name}”.`);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "EchoFlow could not save that search.",
      );
    } finally {
      setSavedBusy(false);
    }
  }

  async function inspectSavedSearch(saved: ResearchSavedSearchResult) {
    setSavedBusy(true);
    setError(null);
    try {
      const inspected = await client.inspectTypedSavedSearch(saved.saved_search_id);
      setEditingSaved(inspected);
      setDraft(intentToDraft(inspected.intent));
      setSavedName(inspected.name);
      setSavedDescription(inspected.description ?? "");
      setStatus(`Loaded “${inspected.name}”.`);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "EchoFlow could not open that saved search.",
      );
    } finally {
      setSavedBusy(false);
    }
  }

  async function replaceSavedIntent() {
    if (!editingSaved) return;
    setSavedBusy(true);
    setError(null);
    try {
      const updated = await client.replaceTypedSavedSearch(
        editingSaved,
        savedName,
        savedDescription.trim() || null,
        draftToIntent(draft),
      );
      setEditingSaved(updated);
      setDraft(intentToDraft(updated.intent));
      setSavedName(updated.name);
      setSavedDescription(updated.description ?? "");
      await loadSavedSearches();
      onResearchChanged?.();
      setStatus(`Updated “${updated.name}”.`);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "EchoFlow could not update that saved search.",
      );
    } finally {
      setSavedBusy(false);
    }
  }

  function newSavedSearch() {
    setEditingSaved(null);
    setSavedName("");
    setSavedDescription("");
    setStatus("The current search can be saved for later.");
  }

  async function createNote(body: string) {
    if (!selectedEvidence) throw new Error("Verified evidence is no longer open.");
    await client.createResearchNote(selectedEvidence, body);
    onResearchChanged?.();
    setStatus("Saved a note to this evidence passage.");
  }

  return (
    <section className="typed-search-shell" aria-labelledby="typed-search-title">
      <div className="typed-search-heading">
        <div>
          <p className="mini-label">Research search</p>
          <h2 id="typed-search-title">What are you looking for?</h2>
          <p>Search transcript evidence, then narrow it with the options you actually need.</p>
        </div>
      </div>

      <form className="typed-search-form" onSubmit={(event) => void executeSearch(event)}>
        <label className="typed-search-query">
          Search
          <input
            type="search"
            required
            maxLength={4096}
            value={draft.queryText}
            onChange={(event) => updateDraft("queryText", event.target.value)}
            placeholder="Words, a phrase, a topic…"
          />
        </label>

        <label className="typed-search-match">
          Match
          <select
            value={draft.match}
            onChange={(event) => updateDraft("match", event.target.value as SearchMatch)}
          >
            <option value="any">Any of these words</option>
            <option value="all">All of these words</option>
            <option value="phrase">Exact phrase</option>
          </select>
        </label>

        <details className="typed-search-options">
          <summary>Search options</summary>
          <div className="typed-search-options-body">
            <fieldset className="typed-search-group typed-search-three">
              <legend>Results</legend>
              <label>
                Search by
                <select
                  value={draft.retrievalMode}
                  onChange={(event) =>
                    updateDraft(
                      "retrievalMode",
                      event.target.value as "lexical" | "semantic" | "hybrid",
                    )
                  }
                >
                  <option value="lexical">Wording</option>
                  <option value="semantic">Meaning</option>
                  <option value="hybrid">Wording + meaning</option>
                </select>
              </label>
              <label>
                Order results by
                <select
                  value={draft.sort}
                  onChange={(event) =>
                    updateDraft("sort", event.target.value as "relevance" | "timeline")
                  }
                >
                  <option value="relevance">Relevance</option>
                  <option value="timeline">Time</option>
                </select>
              </label>
              <label>
                Maximum results
                <input
                  type="number"
                  min={1}
                  max={1000}
                  value={draft.limit}
                  onChange={(event) => updateDraft("limit", event.target.value)}
                />
              </label>
              <label>
                Context around result
                <input
                  type="number"
                  min={0}
                  max={10}
                  value={draft.contextSegments}
                  onChange={(event) => updateDraft("contextSegments", event.target.value)}
                />
              </label>
            </fieldset>

            <fieldset className="typed-search-group typed-search-grid">
              <legend>Transcripts</legend>
              <label>
                Speakers
                <input
                  value={draft.speakerRefs}
                  onChange={(event) => updateDraft("speakerRefs", event.target.value)}
                  placeholder="speaker-1, speaker-2"
                />
              </label>
              <label>
                Languages
                <input
                  value={draft.languages}
                  onChange={(event) => updateDraft("languages", event.target.value)}
                  placeholder="en, fr"
                />
              </label>
              <label className="typed-search-wide">
                Interviews or transcripts
                <input
                  value={draft.documentIds}
                  onChange={(event) => updateDraft("documentIds", event.target.value)}
                  placeholder="interview-42, interview-43"
                />
              </label>
            </fieldset>

            <fieldset className="typed-search-group typed-search-grid">
              <legend>Your research</legend>
              <label>
                Tags
                <input
                  value={draft.tags}
                  onChange={(event) => updateDraft("tags", event.target.value)}
                  placeholder="governance, follow-up"
                />
              </label>
              <label>
                Collections
                <input
                  value={draft.collections}
                  onChange={(event) => updateDraft("collections", event.target.value)}
                  placeholder="Oral histories"
                />
              </label>
              <label className="typed-search-wide">
                Notes containing
                <input
                  value={draft.noteText}
                  onChange={(event) => updateDraft("noteText", event.target.value)}
                  placeholder="follow up"
                />
              </label>
              <label className="typed-search-check typed-search-wide">
                <input
                  type="checkbox"
                  checked={draft.withNotes}
                  onChange={(event) => updateDraft("withNotes", event.target.checked)}
                />
                Only results with notes
              </label>
            </fieldset>

            <p className="typed-search-option-note">
              Meaning and Wording + meaning require a qualified local semantic index. If it
              is not ready, EchoFlow will explain what needs attention rather than silently
              changing the search.
            </p>
          </div>
        </details>

        <div className="typed-search-actions">
          <button type="submit" disabled={busy || savedBusy}>
            {busy ? "Searching…" : "Search"}
          </button>
        </div>
      </form>

      <p className="typed-search-status" aria-live="polite">
        {status}
      </p>
      {error && (
        <p className="error-banner typed-search-error" role="alert">
          {error}
        </p>
      )}

      {result && (
        <div className="typed-search-results">
          <IntentSummary intent={result.intent} />
          <details className="typed-search-technical">
            <summary>Technical details</summary>
            <div className="typed-search-provenance">
              <strong>Retrieval</strong>
              <span>{result.retrieval.mode}</span>
              {result.retrieval.lexical_backend_id && (
                <span>lexical: {result.retrieval.lexical_backend_id}</span>
              )}
              {result.retrieval.semantic_backend_id && (
                <span>semantic: {result.retrieval.semantic_backend_id}</span>
              )}
              {result.retrieval.fusion_profile && (
                <span>fusion: {result.retrieval.fusion_profile}</span>
              )}
              {result.retrieval.semantic_profile && (
                <span>
                  model: {result.retrieval.semantic_profile.model_id} @{" "}
                  {result.retrieval.semantic_profile.resolved_revision}
                </span>
              )}
            </div>
          </details>

          {result.evidence.length === 0 ? (
            <p className="typed-search-empty">No verified transcript passages matched.</p>
          ) : (
            <div className="typed-search-evidence" aria-label="Research search results">
              {result.evidence.map((evidence) => (
                <article
                  key={`${evidence.document_id}:${evidence.canonical_sha256}:${evidence.segment_ids.join(":")}`}
                >
                  <div className="typed-search-result-meta">
                    <strong>{evidence.document_id}</strong>
                    <span>{formatEvidenceTime(evidence.seek_seconds)}</span>
                  </div>
                  <p>{evidence.text}</p>
                  <div className="typed-search-pills">
                    {evidence.speakers.map((speaker) => (
                      <span key={speaker.speaker_ref}>
                        {speaker.display_label ?? speaker.speaker_ref}
                      </span>
                    ))}
                    {evidence.tags.map((tag) => (
                      <span key={`tag:${tag}`}>#{tag}</span>
                    ))}
                    {evidence.collections.map((collection) => (
                      <span key={`collection:${collection}`}>{collection}</span>
                    ))}
                  </div>
                  <button
                    type="button"
                    className="open-evidence-button"
                    onClick={() => setSelectedEvidence(evidence)}
                  >
                    Open evidence
                  </button>
                </article>
              ))}
            </div>
          )}
        </div>
      )}

      {selectedEvidence && (
        <EvidenceReader
          evidence={selectedEvidence}
          generationState="current"
          resultLabel="Research search result"
          onClose={() => setSelectedEvidence(null)}
          onCreateNote={createNote}
        />
      )}

      <section className="typed-saved-searches" aria-labelledby="typed-saved-title">
        <div className="typed-saved-heading">
          <div>
            <p className="mini-label">Saved searches</p>
            <h3 id="typed-saved-title">Save or update this search.</h3>
          </div>
          <button type="button" onClick={newSavedSearch} disabled={savedBusy}>
            New saved search
          </button>
        </div>

        <div className="typed-saved-layout">
          <div className="typed-saved-list" aria-label="Saved searches">
            {savedSearches.length === 0 ? (
              <p>No saved searches yet.</p>
            ) : (
              savedSearches.map((saved) => (
                <button
                  type="button"
                  key={saved.saved_search_id}
                  disabled={savedBusy}
                  aria-pressed={editingSaved?.saved_search_id === saved.saved_search_id}
                  onClick={() => void inspectSavedSearch(saved)}
                >
                  <strong>{saved.name}</strong>
                  <span>{retrievalLabel(saved.retrieval_mode)}</span>
                </button>
              ))
            )}
          </div>

          <div className="typed-saved-editor">
            <label>
              Name
              <input
                value={savedName}
                maxLength={200}
                onChange={(event) => setSavedName(event.target.value)}
                placeholder="A search you want to return to"
              />
            </label>
            <label>
              Description
              <textarea
                value={savedDescription}
                maxLength={4000}
                onChange={(event) => setSavedDescription(event.target.value)}
                placeholder="Optional context"
              />
            </label>
            {editingSaved && <IntentSummary intent={editingSaved.intent} />}
            <p>
              Saving keeps these search choices. Running it later searches the evidence and
              research that exist then; it does not freeze today&apos;s results.
            </p>
            <button
              type="button"
              disabled={savedBusy || busy}
              onClick={() =>
                void (editingSaved ? replaceSavedIntent() : createSavedIntent())
              }
            >
              {savedBusy ? "Saving…" : editingSaved ? "Update saved search" : "Save search"}
            </button>
          </div>
        </div>
      </section>
    </section>
  );
}
