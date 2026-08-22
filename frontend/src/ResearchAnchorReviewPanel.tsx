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
    return "This note points to the current transcript version.";
  }
  if (review.status === "older_verified") {
    return "This note still points to a valid earlier transcript version.";
  }
  return "The transcript version this note points to is not currently available on this computer.";
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
          : "Scholion could not check older note links.",
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
          : "Scholion could not check that note's transcript link.",
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
        "Note moved to the reviewed passage in the current transcript. Its earlier transcript link was kept in the note's history.",
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Scholion could not move that note to the current transcript.",
      );
    } finally {
      setBusyNoteId(null);
    }
  }

  return (
    <section className="research-anchor-review" aria-labelledby="anchor-review-title">
      <div className="research-anchor-review-heading">
        <div>
          <p className="mini-label">Older transcript links</p>
          <h2 id="anchor-review-title">Review notes tied to earlier transcript versions</h2>
          <p>
            Scholion never silently moves a note when a transcript changes. Compare the passage the
            note currently points to with the current transcript, then choose whether to move the
            note.
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
        <p className="research-empty">No notes tied to earlier or unavailable transcript versions need review.</p>
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
                      {note.document_id} · {formatEvidenceTime(note.start_seconds)} · transcript
                      version <code>{shortSha(note.canonical_sha256)}</code>
                    </p>
                  </div>
                  <button type="button" disabled={busy} onClick={() => void review(note)}>
                    {busy ? "Checking…" : reviewed ? "Check again" : "Compare transcript versions"}
                  </button>
                </div>

                {reviewed && (
                  <div className="research-anchor-comparison" aria-live="polite">
                    <p className={`research-anchor-status research-anchor-status-${reviewed.status}`}>
                      {statusCopy(reviewed)}
                    </p>

                    <div className="research-anchor-columns">
                      <section aria-label="Passage this note points to">
                        <p className="mini-label">Passage this note points to</p>
                        {reviewed.anchored ? (
                          <>
                            <p>{reviewed.anchored.text}</p>
                            <small>
                              {formatEvidenceTime(reviewed.anchored.start_seconds)} · version {shortSha(reviewed.anchored.canonical_sha256)}
                            </small>
                          </>
                        ) : (
                          <p className="research-anchor-unavailable">
                            This earlier transcript passage cannot be checked locally right now. The note has not been changed.
                          </p>
                        )}
                      </section>

                      <section aria-label="Current transcript passage">
                        <p className="mini-label">Current transcript passage</p>
                        {reviewed.candidate ? (
                          <>
                            <p>{reviewed.candidate.text}</p>
                            <small>
                              {formatEvidenceTime(reviewed.candidate.start_seconds)} · version {shortSha(reviewed.candidate.canonical_sha256)}
                            </small>
                          </>
                        ) : (
                          <p className="research-anchor-unavailable">
                            Scholion could not find a safe matching passage in the current transcript. The note cannot be moved automatically.
                          </p>
                        )}
                      </section>
                    </div>

                    {reviewed.history.length > 0 && (
                      <details className="research-anchor-history">
                        <summary>Earlier note links ({reviewed.history.length})</summary>
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
                            Move note to this passage
                          </button>
                        ) : (
                          <div
                            className="research-anchor-confirm"
                            role="group"
                            aria-label="Confirm note move"
                          >
                            <p>
                              This note will point to the current transcript passage shown above. Its earlier transcript link will remain in the note's history.
                            </p>
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => void confirmReanchor(note)}
                            >
                              {busy
                                ? "Moving note…"
                                : "Confirm move to current transcript"}
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
