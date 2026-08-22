import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";

import type {
  WorkspaceContextSegment,
  WorkspaceEvidenceResult,
  WorkspaceMatchedWord,
} from "./api/desktop";
import { InfoPopover } from "./components/InfoPopover";
import { EvidencePlayback } from "./EvidencePlayback";
import { formatEvidenceTime } from "./format";
import { usePlaybackClient } from "./PlaybackContext";
import "./evidence-reader.css";

interface EvidenceReaderProps {
  evidence: WorkspaceEvidenceResult;
  onClose: () => void;
  onCreateNote?: ((body: string) => Promise<void>) | undefined;
  generationState?: "current" | "older";
  resultLabel?: string;
}

function wordSeparator(current: WorkspaceMatchedWord, next: WorkspaceMatchedWord | undefined) {
  if (!next) return "";
  if (/\s$/.test(current.text) || /^\s/.test(next.text)) return "";
  if (/^[,.;:!?%)\]}]/.test(next.text)) return "";
  return " ";
}

function renderWords(
  segment: WorkspaceContextSegment,
  onSeek: (seconds: number) => void,
) {
  if (segment.words.length === 0) {
    return segment.text;
  }
  return segment.words.map((word, index) => (
    <span key={`word-wrap:${word.segment_id}:${word.word_index}`}>
      <button
        className="evidence-word-button"
        type="button"
        data-word-index={word.word_index}
        data-word-start={word.start_seconds}
        aria-label={`Move recording position to ${formatEvidenceTime(word.start_seconds)} at ${word.text}`}
        onClick={() => onSeek(word.start_seconds)}
      >
        {word.highlighted ? <mark>{word.text}</mark> : word.text}
      </button>
      {wordSeparator(word, segment.words[index + 1])}
    </span>
  ));
}

export function EvidenceReader({
  evidence,
  onClose,
  onCreateNote,
  generationState = "current",
  resultLabel = "Search result",
}: EvidenceReaderProps) {
  const playback = usePlaybackClient();
  const [cursorSeconds, setCursorSeconds] = useState(evidence.seek_seconds);
  const [noteBody, setNoteBody] = useState("");
  const [savingNote, setSavingNote] = useState(false);
  const [noteError, setNoteError] = useState<string | null>(null);
  const [noteStatus, setNoteStatus] = useState<string | null>(null);

  useEffect(() => {
    setCursorSeconds(evidence.seek_seconds);
    setNoteBody("");
    setNoteError(null);
    setNoteStatus(null);
  }, [evidence]);

  const cursorBounds = useMemo(() => {
    if (evidence.context_segments.length === 0) {
      return { start: evidence.start_seconds, end: evidence.end_seconds };
    }
    return {
      start: Math.min(...evidence.context_segments.map((segment) => segment.start_seconds)),
      end: Math.max(...evidence.context_segments.map((segment) => segment.end_seconds)),
    };
  }, [evidence]);

  async function saveNote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const body = noteBody.trim();
    if (!body) {
      setNoteError("Write a note before saving it.");
      setNoteStatus(null);
      return;
    }
    if (!onCreateNote) {
      setNoteError("This earlier transcript version is available for review, not new notes.");
      return;
    }

    setSavingNote(true);
    setNoteError(null);
    setNoteStatus(null);
    try {
      await onCreateNote(body);
      setNoteBody("");
      setNoteStatus("Note saved to this transcript passage.");
    } catch (caught) {
      setNoteError(
        caught instanceof Error
          ? caught.message
          : "Scholion could not save the note to this transcript passage.",
      );
    } finally {
      setSavingNote(false);
    }
  }

  return (
    <aside className="evidence-reader" aria-labelledby="evidence-reader-title">
      <header className="evidence-reader-header">
        <div>
          <p className="mini-label">Transcript passage</p>
          <h2 id="evidence-reader-title">Evidence reader</h2>
        </div>
        <div className="context-help-actions">
          <InfoPopover
            topic="evidence"
            label="How to use this"
            align="end"
            className="context-help"
          />
          <button type="button" className="quiet-button" onClick={onClose}>
            Close
          </button>
        </div>
      </header>

      <p
        className={`evidence-generation-banner evidence-generation-${generationState}`}
        role="status"
      >
        {generationState === "current"
          ? "Current transcript version"
          : "Earlier transcript version · This is the exact version this research note points to."}
      </p>

      <dl className="evidence-proof">
        <div>
          <dt>Transcript</dt>
          <dd>{evidence.document_id}</dd>
        </div>
        <div>
          <dt>Transcript version ID</dt>
          <dd>
            <code>{evidence.canonical_sha256.slice(0, 12)}…</code>
          </dd>
        </div>
        <div>
          <dt>Passage time</dt>
          <dd>
            {formatEvidenceTime(evidence.start_seconds)}–{formatEvidenceTime(evidence.end_seconds)}
          </dd>
        </div>
      </dl>

      <div className="evidence-context" aria-label="Transcript context">
        {evidence.context_segments.length === 0 ? (
          <section className="context-segment result-segment">
            <div className="context-meta">
              <time dateTime={`PT${evidence.start_seconds}S`}>
                {formatEvidenceTime(evidence.start_seconds)}
              </time>
              <span>{resultLabel}</span>
            </div>
            <p>{evidence.text}</p>
          </section>
        ) : (
          evidence.context_segments.map((segment) => (
            <section
              className={`context-segment${segment.is_result_segment ? " result-segment" : ""}`}
              key={segment.segment_id}
            >
              <div className="context-meta">
                <time dateTime={`PT${segment.start_seconds}S`}>
                  {formatEvidenceTime(segment.start_seconds)}
                </time>
                <span>{segment.is_result_segment ? resultLabel : "Context"}</span>
                {segment.speaker_refs.length > 0 && (
                  <span>{segment.speaker_refs.join(", ")}</span>
                )}
              </div>
              <p>{renderWords(segment, setCursorSeconds)}</p>
            </section>
          ))
        )}
      </div>

      {onCreateNote ? (
        <section className="evidence-note-compose" aria-labelledby="evidence-note-title">
          <div>
            <p className="mini-label">Research note</p>
            <h3 id="evidence-note-title">Attach a note to this passage</h3>
            <p>
              The note will remember this exact transcript version and time range. If the transcript changes before the note is saved, Scholion will ask you to reopen it rather than silently moving the note.
            </p>
          </div>
          <form onSubmit={(event) => void saveNote(event)}>
            <label htmlFor="evidence-research-note">Research note</label>
            <textarea
              id="evidence-research-note"
              value={noteBody}
              maxLength={50_000}
              rows={4}
              placeholder="What matters about this passage?"
              onChange={(event) => setNoteBody(event.target.value)}
            />
            <div className="evidence-note-actions">
              <button type="submit" className="open-evidence-button" disabled={savingNote}>
                {savingNote ? "Saving…" : "Save note"}
              </button>
              {noteStatus && <p role="status">{noteStatus}</p>}
              {noteError && (
                <p className="evidence-note-error" role="alert">
                  {noteError}
                </p>
              )}
            </div>
          </form>
        </section>
      ) : (
        <section className="evidence-note-compose evidence-note-readonly" aria-label="Earlier transcript note policy">
          <p className="mini-label">Earlier transcript version</p>
          <p>
            This version stays available because existing research points to it. New notes are added from the current transcript version instead.
          </p>
        </section>
      )}

      <EvidencePlayback
        client={playback}
        generation={{
          document_id: evidence.document_id,
          canonical_sha256: evidence.canonical_sha256,
        }}
        cursorSeconds={cursorSeconds}
        onPositionChange={setCursorSeconds}
      />

      <footer className="evidence-seek" data-seek-seconds={evidence.seek_seconds}>
        <div>
          <span className="mini-label">Recording position</span>
          <output data-playhead-seconds={cursorSeconds}>
            {formatEvidenceTime(cursorSeconds)}
          </output>
          <button
            type="button"
            className="quiet-button return-to-match"
            onClick={() => setCursorSeconds(evidence.seek_seconds)}
          >
            Return to match
          </button>
        </div>
        <div className="evidence-cursor-control">
          <input
            aria-label="Recording position"
            type="range"
            min={cursorBounds.start}
            max={cursorBounds.end}
            step="0.01"
            value={Math.min(cursorBounds.end, Math.max(cursorBounds.start, cursorSeconds))}
            onChange={(event) => setCursorSeconds(Number(event.target.value))}
          />
          <p>
            Scholion keeps this position tied to the transcript passage and checks the original recording again before playback.
          </p>
        </div>
      </footer>
    </aside>
  );
}
