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
    description: "Removes rebuildable search state. Canonical transcript evidence and the recording stay in place.",
  },
  {
    id: "derived-artifacts",
    label: "Delete derived transcript files",
    description: "Deletes regenerable TXT, SRT, and WebVTT publications next to the canonical transcript.",
  },
  {
    id: "execution-state",
    label: "Delete private processing state",
    description: "Deletes checkpoints and intermediates for this job. Lightweight lifecycle history remains.",
  },
  {
    id: "canonical-transcript",
    label: "Delete canonical transcript evidence",
    description: "Also removes Library search state, derived transcript files, and private execution state. Notes and the original recording are not implied.",
    destructive: true,
  },
  {
    id: "research-notes",
    label: "Delete anchored research notes",
    description: "Deletes human-authored notes anchored to this exact canonical generation. Tags and collections are not globally deleted.",
    destructive: true,
  },
  {
    id: "saved-searches",
    label: "Delete transcript-scoped saved searches",
    description: "Deletes only saved searches that explicitly constrain themselves to this transcript.",
    destructive: true,
  },
  {
    id: "source-recording",
    label: "Delete the original recording",
    description: "Deletes the source media only after Scholion verifies it still matches the bytes used for transcription.",
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
        if (!cancelled) setError(caught instanceof Error ? caught.message : "Could not load lifecycle state");
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
      setError(caught instanceof Error ? caught.message : "Could not apply deletion plan");
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
      setError(caught instanceof Error ? caught.message : "Could not apply cleanup plan");
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
        eyebrow="Local custody"
        title="Storage & deletion"
        theme={theme}
        onThemeChange={onThemeChange}
      />

      <div className="lifecycle-page">
        <div className="lifecycle-intro">
          <div>
            <p className="section-kicker">Review before mutation</p>
            <h2>Nothing here is a one-click mystery delete.</h2>
            <p>
              Scholion asks Python to calculate the exact consequences first. Applying a plan repeats the same request with a token bound to that reviewed state.
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
              <p className="section-kicker">Transcript custody</p>
              <h2 id="transcript-custody-heading">Choose exactly what should leave</h2>
            </div>
            <span className="lifecycle-badge">Plan first</span>
          </div>

          {documents.length === 0 ? (
            <p className="lifecycle-empty">No indexed transcripts are currently available for lifecycle management.</p>
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
                  <span>{selectedDocument.deletion_ready ? "Canonical generation verified in index" : "Library rebuild required before deletion"}</span>
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
                      Scholion will verify that the current source bytes still match transcript provenance before allowing deletion. Filesystem deletion is not a claim of forensic secure erasure.
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
                  Preview deletion plan
                </button>
              </div>
            </>
          )}

          {deletionPlan ? (
            <div className="lifecycle-plan" aria-label="Deletion plan">
              <div className="lifecycle-plan-heading">
                <div>
                  <p className="section-kicker">Backend-calculated plan</p>
                  <h3>Review {deletionPlan.actions.length} planned action{deletionPlan.actions.length === 1 ? "" : "s"}</h3>
                </div>
                <span>{deletionPlan.effective_scopes.length} effective scopes</span>
              </div>

              <ul className="lifecycle-action-list">
                {deletionPlan.actions.map((action, index) => (
                  <li key={`${action.target}-${index}`}>{action.description}</li>
                ))}
              </ul>

              <div className="lifecycle-plan-facts">
                <p>
                  <strong>{deletionPlan.preserved_note_count}</strong> anchored note{deletionPlan.preserved_note_count === 1 ? "" : "s"} preserved by this plan.
                </p>
                <p>
                  <strong>{deletionPlan.affected_saved_search_count}</strong> saved search{deletionPlan.affected_saved_search_count === 1 ? "" : "es"} may be affected by the transcript change.
                </p>
              </div>

              <details>
                <summary>Why did Scholion expand my selection?</summary>
                <p>
                  Requested: {deletionPlan.requested_scopes.map(scopeLabel).join(", ")}. Effective: {deletionPlan.effective_scopes.map(scopeLabel).join(", ")}.
                </p>
                <p>
                  Canonical transcript deletion automatically includes only disposable descendants. Human research and source media still require their own explicit scopes.
                </p>
              </details>

              <button
                className="danger-action"
                type="button"
                disabled={busy}
                onClick={() => void applyDeletion()}
              >
                Apply reviewed plan
              </button>
            </div>
          ) : null}

          {deletionReceipt ? (
            <div className="lifecycle-alert lifecycle-alert-success" role="status">
              Applied custody plan for {deletionReceipt.document_id}. {deletionReceipt.executed_targets.length} target{deletionReceipt.executed_targets.length === 1 ? "" : "s"} changed; {deletionReceipt.preserved_note_count} note{deletionReceipt.preserved_note_count === 1 ? "" : "s"} preserved.
            </div>
          ) : null}
        </section>

        <section className="lifecycle-card" aria-labelledby="retention-heading">
          <div className="lifecycle-card-heading">
            <div>
              <p className="section-kicker">Private processing cleanup</p>
              <h2 id="retention-heading">Clean up old resumable workspaces</h2>
            </div>
            <span className="lifecycle-badge">Evidence-safe</span>
          </div>

          <p className="lifecycle-copy">
            This cleanup applies only to private checkpoints and intermediates under Scholion state. It never age-deletes canonical JSON, original recordings, published transcripts, notes, tags, collections, saved searches, or lifecycle manifests.
          </p>

          <div className="lifecycle-retention-controls">
            <label className="lifecycle-field">
              <span>Remove eligible processing state older than</span>
              <span className="lifecycle-number-field">
                <input
                  aria-label="Execution retention days"
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
                <span>days</span>
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
                <small>These may still be resumable. The preview will mark every candidate whose resume capability would be lost. Running jobs are never eligible.</small>
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
            <div className="lifecycle-plan" aria-label="Retention plan">
              <div className="lifecycle-plan-heading">
                <div>
                  <p className="section-kicker">Backend-calculated cleanup</p>
                  <h3>{retentionPlan.candidates.length} eligible workspace{retentionPlan.candidates.length === 1 ? "" : "s"}</h3>
                </div>
                <span>{retentionPlan.policy.execution_days} day cutoff</span>
              </div>

              {retentionPlan.candidates.length === 0 ? (
                <p className="lifecycle-empty">Nothing currently matches this cleanup policy.</p>
              ) : (
                <ul className="lifecycle-candidate-list">
                  {retentionPlan.candidates.map((candidate) => (
                    <li key={candidate.job_id}>
                      <div>
                        <strong>{candidate.job_id}</strong>
                        <span>{candidate.status} · last updated {candidate.updated_at}</span>
                      </div>
                      {candidate.resume_capability_lost ? (
                        <span className="lifecycle-resume-warning">Resume will be lost</span>
                      ) : (
                        <span>Completed state</span>
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
                Apply cleanup plan
              </button>
            </div>
          ) : null}

          {retentionReceipt ? (
            <div className="lifecycle-alert lifecycle-alert-success" role="status">
              Removed private processing state for {retentionReceipt.discarded_job_ids.length} job{retentionReceipt.discarded_job_ids.length === 1 ? "" : "s"}. Canonical evidence and human research were outside this operation.
            </div>
          ) : null}
        </section>
      </div>
    </>
  );
}
