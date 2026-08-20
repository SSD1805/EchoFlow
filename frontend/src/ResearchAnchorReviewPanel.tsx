import { useCallback, useEffect, useState } from "react";

import type { DesktopClient, ResearchNoteResult } from "./api/desktop";
import { formatEvidenceTime } from "./format";
import {
  reanchorResearchNote,
  reviewResearchAnchor,
  type ResearchAnchorReviewResult,
} from "./researchAnchorApi";
import "./research-anchor-review.css";

interface ResearchAnchorReviewPanelProps {
  client: DesktopClient;
  onReanchored: () => void;
}

function statusCopy(review: ResearchAnchorReviewResult): string {
  if (review.status === "current_verified") {
    return "This note now cites the current verified canonical generation.";
  }
  if (review.status === "older_verified") {
    return "The stored evidence still verifies, but it belongs to an older canonical generation.";
  }
  return "The stored canonical evidence cannot currently be verified on this machine.";
}

function shortSha(value: string): string {
  return `${value.slice(0, 10)}…${value.slice(-6)}`;
}

export function ResearchAnchorReviewPanel({
  client,
  onReanchored,
}: ResearchAnchorReviewPanelProps) {
  const [notes, setNotes] = useState<ResearchNoteResult[]>([]);
  const [reviews, setReviews] = useState<Record<string, ResearchAnchorReviewResult>>({});
  const [confirmingNoteId, setConfirmingNoteId] = useState<string | null>(null);
  const [busyNoteId, setBusyNoteId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const loadReviewable = useCallback(async () => {
    const overview = await client.researchOverview();
    setNotes(overview.notes.filter((note) => !note.current));
  }, [client]);

  useEffect(() => {
    void loadReviewable().catch((caught) => {
      setError(
        caught instanceof Error
          ? caught.message
          : "EchoFlow could not inspect research anchors.",
      );
    });
  }, [loadReviewable]);

  async function review(note: ResearchNoteResult) {
    setBusyNoteId(note.note_id);
    setConfirmingNoteId(null);
    setError(null);
    setMessage(null);
    try {
      const result = await reviewResearchAnchor(note);
      setReviews((current) => ({ ...current, [note.note_id]: result }));
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "EchoFlow could not review that evidence anchor.",
      );
    } finally {
      setBusyNoteId(null);
    }
  }

  async function confirmReanchor(note: ResearchNoteResult) {
    const reviewed = reviews[note.note_id];
    if (!reviewed?.candidate) return;
    setBusyNoteId(note.note_id);
    setError(null);
    setMessage(null);
    try {
      await reanchorResearchNote(reviewed);
      setConfirmingNoteId(null);
      setNotes((current) => current.filter((item) => item.note_id !== note.note_id));
      setReviews((current) => {
        const next = { ...current };
        delete next[note.note_id];
        return next;
      });
      onReanchored();
      setMessage(
        "Note re-anchored to the reviewed current generation. The prior anchor was preserved in durable history.",
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "EchoFlow could not re-anchor that note.",
      );
    } finally {
      setBusyNoteId(null);
    }
  }

  return (
    <section className="research-anchor-review" aria-labelledby="anchor-review-title">
      <div className="research-anchor-review-heading">
        <div>
          <p className="mini-label">Evidence maintenance</p>
          <h2 id="anchor-review-title">Review older or unavailable note anchors</h2>
          <p>
            EchoFlow never silently moves research to a newer transcript. Review the stored
            evidence and any current-generation candidate first, then explicitly confirm a
            re-anchor if the candidate is correct.
          </p>
        </div>
        <span className="research-count" aria-label={`${notes.length} notes need review`}>
          {notes.length}
        </span>
      </div>

      {message && (
        <p className="research-mutation-status" aria-live="polite">
          {message}
        </p>
      )}
      {error && (
        <p className="error-banner research-error" role="alert">
          {error}
        </p>
      )}

      {notes.length === 0 ? (
        <p className="research-empty">No older or unavailable anchors need review.</p>
      ) : (
        <div className="research-anchor-review-list">
          {notes.map((note) => {
            const reviewed = reviews[note.note_id];
            const confirming = confirmingNoteId === note.note_id;
            const busy = busyNoteId === note.note_id;
            return (
              <article key={note.note_id} className="research-anchor-card">
                <div className="research-anchor-card-header">
                  <div>
                    <strong>{note.body}</strong>
                    <p>
                      {note.document_id} · {formatEvidenceTime(note.start_seconds)} · stored
                      generation <code>{shortSha(note.canonical_sha256)}</code>
                    </p>
                  </div>
                  <button type="button" disabled={busy} onClick={() => void review(note)}>
                    {busy ? "Reviewing…" : reviewed ? "Review again" : "Review evidence status"}
                  </button>
                </div>

                {reviewed && (
                  <div className="research-anchor-comparison" aria-live="polite">
                    <p className={`research-anchor-status research-anchor-status-${reviewed.status}`}>
                      {statusCopy(reviewed)}
                    </p>

                    <div className="research-anchor-columns">
                      <section aria-label="Stored anchor">
                        <p className="mini-label">Stored anchor</p>
                        {reviewed.anchored ? (
                          <>
                            <p>{reviewed.anchored.text}</p>
                            <small>
                              {formatEvidenceTime(reviewed.anchored.start_seconds)} · {shortSha(reviewed.anchored.canonical_sha256)}
                            </small>
                          </>
                        ) : (
                          <p className="research-anchor-unavailable">
                            Stored evidence cannot be verified locally. The durable anchor has not been changed.
                          </p>
                        )}
                      </section>

                      <section aria-label="Current candidate">
                        <p className="mini-label">Current-generation candidate</p>
                        {reviewed.candidate ? (
                          <>
                            <p>{reviewed.candidate.text}</p>
                            <small>
                              {formatEvidenceTime(reviewed.candidate.start_seconds)} · {shortSha(reviewed.candidate.canonical_sha256)}
                            </small>
                          </>
                        ) : (
                          <p className="research-anchor-unavailable">
                            EchoFlow could not derive a safe same-source current candidate. No re-anchor action is available.
                          </p>
                        )}
                      </section>
                    </div>

                    {reviewed.history.length > 0 && (
                      <details className="research-anchor-history">
                        <summary>Previous anchors ({reviewed.history.length})</summary>
                        <ol>
                          {reviewed.history.map((entry) => (
                            <li key={entry.revision}>
                              Revision {entry.revision} · {shortSha(entry.canonical_sha256)} · replaced {new Date(entry.replaced_at).toLocaleString()}
                            </li>
                          ))}
                        </ol>
                      </details>
                    )}

                    {reviewed.candidate && reviewed.status !== "current_verified" && (
                      <div className="research-anchor-actions">
                        {!confirming ? (
                          <button
                            type="button"
                            className="research-anchor-prepare"
                            onClick={() => setConfirmingNoteId(note.note_id)}
                          >
                            Prepare re-anchor
                          </button>
                        ) : (
                          <div
                            className="research-anchor-confirm"
                            role="group"
                            aria-label="Confirm re-anchor"
                          >
                            <p>
                              This changes the note’s current evidence pointer to the candidate above. The existing anchor will be retained as immutable history.
                            </p>
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => void confirmReanchor(note)}
                            >
                              {busy
                                ? "Re-anchoring…"
                                : "Confirm re-anchor to reviewed candidate"}
                            </button>
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => setConfirmingNoteId(null)}
                            >
                              Cancel
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
