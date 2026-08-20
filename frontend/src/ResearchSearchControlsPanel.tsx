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

interface SearchDraft {
  queryText: string;
  phrase: boolean;
  operator: "any" | "all";
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
  phrase: false,
  operator: "any",
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

function draftToIntent(draft: SearchDraft): ResearchSearchIntent {
  return {
    query_text: draft.queryText,
    phrase: draft.phrase,
    operator: draft.operator,
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
    phrase: intent.phrase,
    operator: intent.operator,
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

function IntentSummary({ intent }: { intent: ResearchSearchIntent }) {
  const chips = [
    `phrase: ${intent.phrase ? "exact" : "off"}`,
    `operator: ${intent.operator.toUpperCase()}`,
    `mode: ${intent.retrieval_mode}`,
    `sort: ${intent.sort}`,
    `limit: ${intent.limit}`,
    `context: ${intent.context_segments}`,
    ...intent.speaker_refs.map((value) => `speaker: ${value}`),
    ...intent.languages.map((value) => `language: ${value}`),
    ...intent.document_ids.map((value) => `transcript: ${value}`),
    ...intent.tags.map((value) => `tag: ${value}`),
    ...intent.collections.map((value) => `collection: ${value}`),
    ...(intent.note_text ? [`note text: ${intent.note_text}`] : []),
    ...(intent.with_notes ? ["must have research notes"] : []),
  ];

  return (
    <div className="typed-search-intent" aria-label="Applied search intent">
      <strong>Applied by EchoFlow</strong>
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
  const [status, setStatus] = useState(
    "Compose a typed evidence query. Python owns how every control is interpreted.",
  );

  const loadSavedSearches = useCallback(async () => {
    const overview = await client.researchOverview();
    setSavedSearches(overview.saved_searches);
  }, [client]);

  useEffect(() => {
    void loadSavedSearches().catch((caught) => {
      setError(
        caught instanceof Error
          ? caught.message
          : "EchoFlow could not read saved search metadata.",
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
        `${next.evidence.length} verified evidence result${next.evidence.length === 1 ? "" : "s"}. EchoFlow returned the canonicalized intent shown below.`,
      );
    } catch (caught) {
      setResult(null);
      setError(
        caught instanceof Error
          ? caught.message
          : "EchoFlow could not execute that typed research search.",
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
      setStatus(`Saved “${saved.name}” with its full typed search intent.`);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "EchoFlow could not save that typed research search.",
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
      setStatus(`Loaded “${inspected.name}” into the typed intent editor.`);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "EchoFlow could not inspect that saved search.",
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
      setStatus(
        `Updated “${updated.name}”. Display metadata and typed query intent committed together.`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "EchoFlow could not update that saved search.",
      );
    } finally {
      setSavedBusy(false);
    }
  }

  function newSavedSearch() {
    setEditingSaved(null);
    setSavedName("");
    setSavedDescription("");
    setStatus("The current typed controls can be saved as a new durable research question.");
  }

  async function createNote(body: string) {
    if (!selectedEvidence) throw new Error("Verified evidence is no longer open.");
    await client.createResearchNote(selectedEvidence, body);
    onResearchChanged?.();
    setStatus("Saved a research note to the verified current evidence window.");
  }

  return (
    <section className="typed-search-shell" aria-labelledby="typed-search-title">
      <div className="typed-search-heading">
        <div>
          <p className="mini-label">Advanced evidence search</p>
          <h2 id="typed-search-title">Make the question inspectable.</h2>
          <p>
            These controls are presentation only. Python validates and executes the complete
            intent, including research-state constraints and retrieval mode.
          </p>
        </div>
        <span className="typed-search-authority">Python authority</span>
      </div>

      <form className="typed-search-form" onSubmit={(event) => void executeSearch(event)}>
        <label className="typed-search-query">
          Query
          <input
            type="search"
            required
            maxLength={4096}
            value={draft.queryText}
            onChange={(event) => updateDraft("queryText", event.target.value)}
            placeholder="What evidence are you looking for?"
          />
        </label>

        <fieldset className="typed-search-group">
          <legend>Text matching</legend>
          <label className="typed-search-check">
            <input
              type="checkbox"
              checked={draft.phrase}
              onChange={(event) => updateDraft("phrase", event.target.checked)}
            />
            Exact phrase
          </label>
          <label>
            Term operator
            <select
              value={draft.operator}
              onChange={(event) =>
                updateDraft("operator", event.target.value as "any" | "all")
              }
            >
              <option value="any">ANY term</option>
              <option value="all">ALL terms</option>
            </select>
          </label>
        </fieldset>

        <fieldset className="typed-search-group typed-search-three">
          <legend>Retrieval and result shape</legend>
          <label>
            Retrieval mode
            <select
              value={draft.retrievalMode}
              onChange={(event) =>
                updateDraft(
                  "retrievalMode",
                  event.target.value as "lexical" | "semantic" | "hybrid",
                )
              }
            >
              <option value="lexical">Lexical</option>
              <option value="semantic">Semantic</option>
              <option value="hybrid">Hybrid</option>
            </select>
          </label>
          <label>
            Sort
            <select
              value={draft.sort}
              onChange={(event) =>
                updateDraft("sort", event.target.value as "relevance" | "timeline")
              }
            >
              <option value="relevance">Relevance</option>
              <option value="timeline">Timeline</option>
            </select>
          </label>
          <label>
            Result limit
            <input
              type="number"
              min={1}
              max={1000}
              value={draft.limit}
              onChange={(event) => updateDraft("limit", event.target.value)}
            />
          </label>
          <label>
            Context segments
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
          <legend>Transcript evidence filters</legend>
          <label>
            Speaker refs
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
            Transcript IDs
            <input
              value={draft.documentIds}
              onChange={(event) => updateDraft("documentIds", event.target.value)}
              placeholder="interview-42, interview-43"
            />
          </label>
        </fieldset>

        <fieldset className="typed-search-group typed-search-grid">
          <legend>Research-state filters</legend>
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
            Note text
            <input
              value={draft.noteText}
              onChange={(event) => updateDraft("noteText", event.target.value)}
              placeholder="Only evidence related to notes containing…"
            />
          </label>
          <label className="typed-search-check typed-search-wide">
            <input
              type="checkbox"
              checked={draft.withNotes}
              onChange={(event) => updateDraft("withNotes", event.target.checked)}
            />
            Require associated research notes
          </label>
        </fieldset>

        <div className="typed-search-actions">
          <button type="submit" disabled={busy || savedBusy}>
            {busy ? "Searching…" : "Run typed search"}
          </button>
          <p>
            Semantic and hybrid modes require qualified local semantic state. EchoFlow will
            refuse the request if that backend state is unavailable or stale.
          </p>
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
          <div className="typed-search-provenance">
            <strong>Retrieval provenance</strong>
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
                model: {result.retrieval.semantic_profile.model_id} @ {result.retrieval.semantic_profile.resolved_revision}
              </span>
            )}
          </div>

          {result.evidence.length === 0 ? (
            <p className="typed-search-empty">No current verified evidence matched.</p>
          ) : (
            <div className="typed-search-evidence" aria-label="Typed search evidence results">
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
                    Open verified evidence
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
          resultLabel="Typed search result"
          onClose={() => setSelectedEvidence(null)}
          onCreateNote={createNote}
        />
      )}

      <section className="typed-saved-searches" aria-labelledby="typed-saved-title">
        <div className="typed-saved-heading">
          <div>
            <p className="mini-label">Durable questions</p>
            <h3 id="typed-saved-title">Save or revise the whole intent.</h3>
          </div>
          <button type="button" onClick={newSavedSearch} disabled={savedBusy}>
            New saved search
          </button>
        </div>

        <div className="typed-saved-layout">
          <div className="typed-saved-list" aria-label="Saved searches available to edit">
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
                  <span>{saved.retrieval_mode}</span>
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
                placeholder="A durable research question"
              />
            </label>
            <label>
              Description
              <textarea
                value={savedDescription}
                maxLength={4000}
                onChange={(event) => setSavedDescription(event.target.value)}
                placeholder="Optional context for future you"
              />
            </label>
            {editingSaved && <IntentSummary intent={editingSaved.intent} />}
            <p>
              Saving uses the controls above. EchoFlow validates and stores them as typed
              intent, never as a rendered command or frozen result list.
            </p>
            <button
              type="button"
              disabled={savedBusy || busy}
              onClick={() =>
                void (editingSaved ? replaceSavedIntent() : createSavedIntent())
              }
            >
              {savedBusy
                ? "Saving…"
                : editingSaved
                  ? "Save metadata + typed intent"
                  : "Save current typed intent"}
            </button>
          </div>
        </div>
      </section>
    </section>
  );
}
