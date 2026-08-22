import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  DeletionPlan,
  DeletionReceipt,
  DeletionScope,
  LifecycleClient,
  LifecycleDocument,
  RetentionPlan,
  RetentionReceipt,
} from "./api/lifecycle";
import { InfoPopover } from "./components/InfoPopover";
import { type Theme, WorkspaceHeader } from "./components/WorkspaceHeader";

interface LifecycleWorkspaceProps {
  lifecycle: LifecycleClient;
  theme: Theme;
  onThemeChange: (theme: Theme) => void;
}

interface ScopeCopy {
  id: DeletionScope;
  label: string;
  description: string;
  destructive?: boolean;
}

const SCOPE_COPY: readonly ScopeCopy[] = [
  {
    id: "library-view",
    label: "Remove from Library search",
    description: "Removes this transcript from search results. The transcript file and original recording stay in place.",
  },
  {
    id: "derived-artifacts",
    label: "Delete exported transcript copies",
    description: "Deletes TXT, SRT, and WebVTT copies. The main Scholion transcript stays in place.",
  },
  {
    id: "execution-state",
    label: "Delete temporary processing files",
    description: "Deletes saved progress and temporary files from transcription. Finished transcripts stay in place.",
  },
  {
    id: "canonical-transcript",
    label: "Delete the Scholion transcript",
    description: "Also removes its Library search entries, exported copies, and temporary processing files. Notes and the original recording stay unless you select them separately.",
    destructive: true,
  },
  {
    id: "research-notes",
    label: "Delete notes attached to this transcript",
    description: "Deletes your notes attached to this version of the transcript. Tags and collections elsewhere are not deleted.",
    destructive: true,
  },
  {
    id: "saved-searches",
    label: "Delete saved searches limited to this transcript",
    description: "Deletes only saved searches that were specifically limited to this transcript.",
    destructive: true,
  },
  {
    id: "source-recording",
    label: "Delete the original recording",
    description: "Before deleting it, Scholion checks that the file is the same recording that was used for transcription.",
    destructive: true,
  },
];

function documentLabel(document: LifecycleDocument): string {
  return document.source_name ? `${document.source_name} · ${document.document_id}` : document.document_id;
}

function scopeLabel(scope: DeletionScope): string {
  return SCOPE_COPY.find((item) => item.id === scope)?.label ?? scope;
}

export function LifecycleWorkspace({
  lifecycle,
  theme,
  onThemeChange,
}: LifecycleWorkspaceProps) {
  const [documents, setDocuments] = useState<LifecycleDocument[]>([]);
  const [selectedDocumentId, setSelectedDocumentId] = useState("");
  const [selectedScopes, setSelectedScopes] = useState<DeletionScope[]>([]);
  const [sourceAcknowledged, setSourceAcknowledged] = useState(false);
  const [deletionPlan, setDeletionPlan] = useState<DeletionPlan | null>(null);
  const [deletionReceipt, setDeletionReceipt] = useState<DeletionReceipt | null>(null);
  const [executionDays, setExecutionDays] = useState("30");
  const [includeIncomplete, setIncludeIncomplete] = useState(false);
  const [retentionPlan, setRetentionPlan] = useState<RetentionPlan | null>(null);
  const [retentionReceipt, setRetentionReceipt] = useState<RetentionReceipt | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedDocument = useMemo(
    () => documents.find((item) => item.document_id === selectedDocumentId) ?? null,
    [documents, selectedDocumentId],
  );
  const sourceSelected = selectedScopes.includes("source-recording");

  const loadDocuments = useCallback(async () => {
    const loaded = await lifecycle.documents();
    setDocuments(loaded);
    setSelectedDocumentId((current) =>
      loaded.some((item) => item.document_id === current)
        ? current
        : (loaded[0]?.document_id ?? ""),
    );
  }, [lifecycle]);

  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    lifecycle
      .documents()
      .then((loaded) => {
        if (cancelled) return;
        setDocuments(loaded);
        setSelectedDocumentId(loaded[0]?.document_id ?? "");
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof Error ? caught.message : "Could not load storage and deletion data");
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [lifecycle]);

  function resetDeletionReview() {
    setDeletionPlan(null);
    setDeletionReceipt(null);
    setError(null);
  }

  function resetRetentionReview() {
    setRetentionPlan(null);
    setRetentionReceipt(null);
    setError(null);
  }

  function selectDocument(documentId: string) {
    setSelectedDocumentId(documentId);
    setSelectedScopes([]);
    setSourceAcknowledged(false);
    resetDeletionReview();
  }

  function toggleScope(scope: DeletionScope) {
    setSelectedScopes((current) =>
      current.includes(scope) ? current.filter((item) => item !== scope) : [...current, scope],
    );
    if (scope === "source-recording") setSourceAcknowledged(false);
    resetDeletionReview();
  }

  async function previewDeletion() {
    if (!selectedDocument || selectedScopes.length === 0) return;
    setBusy(true);
    setError(null);
    setDeletionReceipt(null);
    try {
      setDeletionPlan(
        await lifecycle.planDeletion(
          selectedDocument.document_id,
          selectedScopes,
          sourceSelected && sourceAcknowledged,
        ),
      );
    } catch (caught) {
      setDeletionPlan(null);
      setError(caught instanceof Error ? caught.message : "Could not preview deletion");
    } finally {
      setBusy(false);
    }
  }

  async function applyDeletion() {
    if (!deletionPlan) return;
    setBusy(true);
    setError(null);
    try {
      const receipt = await lifecycle.executeDeletion(
        deletionPlan,
        sourceSelected && sourceAcknowledged,
      );
      setDeletionReceipt(receipt);
      setDeletionPlan(null);
      setSelectedScopes([]);
      setSourceAcknowledged(false);
      await loadDocuments();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not delete the selected items");
    } finally {
      setBusy(false);
    }
  }

  async function previewRetention() {
    const days = Number(executionDays);
    setBusy(true);
    setError(null);
    setRetentionReceipt(null);
    try {
      setRetentionPlan(
        await lifecycle.planRetention({
          executionDays: days,
          includeIncomplete,
        }),
      );
    } catch (caught) {
      setRetentionPlan(null);
      setError(caught instanceof Error ? caught.message : "Could not preview cleanup");
    } finally {
      setBusy(false);
    }
  }

  async function applyRetention() {
    if (!retentionPlan) return;
    setBusy(true);
    setError(null);
    try {
      setRetentionReceipt(await lifecycle.executeRetention(retentionPlan));
      setRetentionPlan(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not remove temporary processing files");
    } finally {
      setBusy(false);
    }
  }

  const deletionPreviewDisabled =
    busy ||
    !selectedDocument?.deletion_ready ||
    selectedScopes.length === 0 ||
    (sourceSelected && !sourceAcknowledged);

  return (
    <>
      <WorkspaceHeader
        eyebrow="Storage"
        title="Storage & deletion"
        theme={theme}
        onThemeChange={onThemeChange}
      />

      <div className="lifecycle-page">
        <div className="lifecycle-intro">
          <div>
            <p className="section-kicker">Choose what to remove</p>
            <h2>See exactly what will be deleted before anything changes.</h2>
            <p>
              Select the items you want to remove. Scholion shows the full deletion list for you to review before you confirm it.
            </p>
          </div>
          <InfoPopover topic="storage" label="How storage controls work" />
        </div>

        {error ? (
          <div className="lifecycle-alert lifecycle-alert-error" role="alert">
            {error}
          </div>
        ) : null}

        <section className="lifecycle-card" aria-labelledby="transcript-custody-heading">
          <div className="lifecycle-card-heading">
            <div>
              <p className="section-kicker">Transcript files and research</p>
              <h2 id="transcript-custody-heading">Choose what you want to delete</h2>
            </div>
            <span className="lifecycle-badge">Preview required</span>
          </div>

          {documents.length === 0 ? (
            <p className="lifecycle-empty">No transcripts are currently available here. Transcripts appear after they have been added to Library search.</p>
          ) : (
            <>
              <label className="lifecycle-field">
                <span>Transcript</span>
                <select
                  aria-label="Transcript to manage"
                  value={selectedDocumentId}
                  disabled={busy}
                  onChange={(event) => selectDocument(event.target.value)}
                >
                  {documents.map((document) => (
                    <option key={document.document_id} value={document.document_id}>
                      {documentLabel(document)}
                    </option>
                  ))}
                </select>
              </label>

              {selectedDocument ? (
                <div className="lifecycle-document-facts" aria-label="Selected transcript facts">
                  <span>{selectedDocument.segment_count.toLocaleString()} segments</span>
                  <span>{selectedDocument.detected_language ?? "Language unavailable"}</span>
                  <span>{selectedDocument.deletion_ready ? "Ready for deletion review" : "Refresh Library search before deleting"}</span>
                </div>
              ) : null}

              <fieldset className="lifecycle-scopes">
                <legend>What do you want to remove?</legend>
                {SCOPE_COPY.map((scope) => (
                  <label
                    key={scope.id}
                    className={scope.destructive ? "lifecycle-scope lifecycle-scope-destructive" : "lifecycle-scope"}
                  >
                    <input
                      type="checkbox"
                      checked={selectedScopes.includes(scope.id)}
                      disabled={busy}
                      onChange={() => toggleScope(scope.id)}
                    />
                    <span>
                      <strong>{scope.label}</strong>
                      <small>{scope.description}</small>
                    </span>
                  </label>
                ))}
              </fieldset>

              {sourceSelected ? (
                <label className="lifecycle-source-guard">
                  <input
                    type="checkbox"
                    checked={sourceAcknowledged}
                    disabled={busy}
                    onChange={(event) => {
                      setSourceAcknowledged(event.target.checked);
                      resetDeletionReview();
                    }}
                  />
                  <span>
                    <strong>I understand this deletes the original recording.</strong>
                    <small>
                      Scholion first checks that the current file is the same recording used for transcription. Normal file deletion is not secure forensic erasure.
                    </small>
                  </span>
                </label>
              ) : null}

              <div className="lifecycle-actions">
                <button
                  className="secondary-action"
                  type="button"
                  disabled={deletionPreviewDisabled}
                  onClick={() => void previewDeletion()}
                >
                  Review what will be deleted
                </button>
              </div>
            </>
          )}

          {deletionPlan ? (
            <div className="lifecycle-plan" aria-label="Deletion preview">
              <div className="lifecycle-plan-heading">
                <div>
                  <p className="section-kicker">Deletion preview</p>
                  <h3>Review {deletionPlan.actions.length} item{deletionPlan.actions.length === 1 ? "" : "s"} to be removed</h3>
                </div>
              </div>

              <ul className="lifecycle-action-list">
                {deletionPlan.actions.map((action, index) => (
                  <li key={`${action.target}-${index}`}>{action.description}</li>
                ))}
              </ul>

              <div className="lifecycle-plan-facts">
                <p>
                  <strong>{deletionPlan.preserved_note_count}</strong> note{deletionPlan.preserved_note_count === 1 ? "" : "s"} will stay.
                </p>
                <p>
                  <strong>{deletionPlan.affected_saved_search_count}</strong> saved search{deletionPlan.affected_saved_search_count === 1 ? "" : "es"} may refer to this transcript.
                </p>
              </div>

              <details>
                <summary>Why are extra items included?</summary>
                <p>
                  You selected: {deletionPlan.requested_scopes.map(scopeLabel).join(", ")}. Scholion will remove: {deletionPlan.effective_scopes.map(scopeLabel).join(", ")}.
                </p>
                <p>
                  Deleting a Scholion transcript also removes its rebuildable search entries, exported copies, and temporary processing files. Your notes and original recording still require their own separate selection.
                </p>
              </details>

              <button
                className="danger-action"
                type="button"
                disabled={busy}
                onClick={() => void applyDeletion()}
              >
                Delete these items
              </button>
            </div>
          ) : null}

          {deletionReceipt ? (
            <div className="lifecycle-alert lifecycle-alert-success" role="status">
              Deleted {deletionReceipt.executed_targets.length} item{deletionReceipt.executed_targets.length === 1 ? "" : "s"} for {deletionReceipt.document_id}. {deletionReceipt.preserved_note_count} note{deletionReceipt.preserved_note_count === 1 ? "" : "s"} kept.
            </div>
          ) : null}
        </section>

        <section className="lifecycle-card" aria-labelledby="retention-heading">
          <div className="lifecycle-card-heading">
            <div>
              <p className="section-kicker">Temporary processing files</p>
              <h2 id="retention-heading">Clean up old transcription work files</h2>
            </div>
            <span className="lifecycle-badge">Finished transcripts stay</span>
          </div>

          <p className="lifecycle-copy">
            This cleanup removes only saved progress and temporary processing files. It does not age-delete finished Scholion transcripts, exported copies, original recordings, notes, tags, collections, or saved searches.
          </p>

          <div className="lifecycle-retention-controls">
            <label className="lifecycle-field">
              <span>Remove completed-job temporary files last updated more than</span>
              <span className="lifecycle-number-field">
                <input
                  aria-label="Temporary processing file age in days"
                  type="number"
                  min="0"
                  max="36500"
                  value={executionDays}
                  disabled={busy}
                  onChange={(event) => {
                    setExecutionDays(event.target.value);
                    resetRetentionReview();
                  }}
                />
                <span>days ago</span>
              </span>
            </label>

            <label className="lifecycle-source-guard lifecycle-incomplete-guard">
              <input
                type="checkbox"
                checked={includeIncomplete}
                disabled={busy}
                onChange={(event) => {
                  setIncludeIncomplete(event.target.checked);
                  resetRetentionReview();
                }}
              />
              <span>
                <strong>Also include failed and interrupted jobs</strong>
                <small>Some of these jobs may still be resumable. The preview identifies any job that would lose saved progress. Running jobs are never included.</small>
              </span>
            </label>
          </div>

          <button
            className="secondary-action"
            type="button"
            disabled={busy || executionDays.trim() === ""}
            onClick={() => void previewRetention()}
          >
            Preview cleanup
          </button>

          {retentionPlan ? (
            <div className="lifecycle-plan" aria-label="Cleanup preview">
              <div className="lifecycle-plan-heading">
                <div>
                  <p className="section-kicker">Cleanup preview</p>
                  <h3>{retentionPlan.candidates.length} job{retentionPlan.candidates.length === 1 ? "" : "s"} eligible</h3>
                </div>
                <span>Last updated more than {retentionPlan.policy.execution_days} days ago</span>
              </div>

              {retentionPlan.candidates.length === 0 ? (
                <p className="lifecycle-empty">Nothing currently matches these cleanup settings.</p>
              ) : (
                <ul className="lifecycle-candidate-list">
                  {retentionPlan.candidates.map((candidate) => (
                    <li key={candidate.job_id}>
                      <div>
                        <strong>{candidate.job_id}</strong>
                        <span>{candidate.status} · last updated {candidate.updated_at}</span>
                      </div>
                      {candidate.resume_capability_lost ? (
                        <span className="lifecycle-resume-warning">Saved progress will be lost</span>
                      ) : (
                        <span>Completed</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}

              <button
                className="danger-action"
                type="button"
                disabled={busy || retentionPlan.candidates.length === 0}
                onClick={() => void applyRetention()}
              >
                Remove these temporary files
              </button>
            </div>
          ) : null}

          {retentionReceipt ? (
            <div className="lifecycle-alert lifecycle-alert-success" role="status">
              Removed temporary processing files for {retentionReceipt.discarded_job_ids.length} job{retentionReceipt.discarded_job_ids.length === 1 ? "" : "s"}. Finished transcripts and research were unchanged.
            </div>
          ) : null}
        </section>
      </div>
    </>
  );
}
