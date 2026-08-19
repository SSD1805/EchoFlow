import { useEffect, useMemo, useState } from "react";

import type { WorkspaceEvidenceResult } from "./api/desktop";

interface EvidenceReaderProps {
  evidence: WorkspaceEvidenceResult;
  onClose: () => void;
}

function formatTime(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remaining = total % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(remaining).padStart(2, "0")}`;
  }
  return `${minutes}:${String(remaining).padStart(2, "0")}`;
}

function speakerLabel(evidence: WorkspaceEvidenceResult, speakerRef: string | null): string {
  if (!speakerRef) return "Speaker unknown";
  const speaker = evidence.speakers.find((item) => item.speaker_ref === speakerRef);
  return speaker?.display_label ?? speakerRef;
}

export function EvidenceReader({ evidence, onClose }: EvidenceReaderProps) {
  const [cursorSeconds, setCursorSeconds] = useState(evidence.seek_seconds);

  useEffect(() => {
    setCursorSeconds(evidence.seek_seconds);
  }, [evidence]);

  const cursorBounds = useMemo(() => {
    const segments = evidence.context_segments;
    if (segments.length === 0) {
      return { start: evidence.start_seconds, end: evidence.end_seconds };
    }
    return {
      start: Math.min(...segments.map((item) => item.start_seconds)),
      end: Math.max(...segments.map((item) => item.end_seconds)),
    };
  }, [evidence]);

  return (
    <aside className="evidence-reader" aria-labelledby="evidence-reader-title">
      <div className="reader-heading">
        <div>
          <p className="mini-label">Verified canonical context</p>
          <h2 id="evidence-reader-title">Evidence reader</h2>
        </div>
        <button className="reader-close" type="button" onClick={onClose} aria-label="Close evidence reader">
          Close
        </button>
      </div>

      <div className="reader-identity">
        <div>
          <span>Transcript</span>
          <strong>{evidence.document_id}</strong>
        </div>
        <div>
          <span>Canonical generation</span>
          <code title={evidence.canonical_sha256}>{evidence.canonical_sha256.slice(0, 12)}…</code>
        </div>
      </div>

      <div className="reader-transcript" aria-label="Verified transcript context">
        {evidence.context_segments.map((segment) => (
          <section
            className={segment.is_result_segment ? "reader-segment reader-segment-result" : "reader-segment"}
            key={segment.segment_id}
            data-result-segment={segment.is_result_segment ? "true" : "false"}
          >
            <div className="reader-segment-meta">
              <time dateTime={`PT${segment.start_seconds}S`}>{formatTime(segment.start_seconds)}</time>
              <span>{segment.segment_id}</span>
              {segment.speaker_refs.length > 0 && (
                <span>{segment.speaker_refs.map((ref) => speakerLabel(evidence, ref)).join(", ")}</span>
              )}
            </div>

            {segment.words.length > 0 ? (
              <p className="reader-words">
                {segment.words.map((word) => (
                  <button
                    className={word.highlighted ? "reader-word reader-word-highlighted" : "reader-word"}
                    type="button"
                    key={`${word.segment_id}:${word.word_index}`}
                    data-highlighted={word.highlighted ? "true" : "false"}
                    data-word-start={word.start_seconds}
                    aria-label={`Move evidence cursor to ${formatTime(word.start_seconds)} at ${word.text}`}
                    onClick={() => setCursorSeconds(word.start_seconds)}
                  >
                    {word.text}
                  </button>
                ))}
              </p>
            ) : (
              <p className="reader-segment-text">{segment.text}</p>
            )}
          </section>
        ))}
      </div>

      <div className="evidence-cursor" aria-label="Verified evidence position">
        <div className="cursor-copy">
          <div>
            <p className="mini-label">Source-relative evidence cursor</p>
            <output data-playhead-seconds={cursorSeconds}>{formatTime(cursorSeconds)}</output>
          </div>
          <button type="button" onClick={() => setCursorSeconds(evidence.seek_seconds)}>
            Return to match
          </button>
        </div>
        <input
          aria-label="Evidence position"
          type="range"
          min={cursorBounds.start}
          max={cursorBounds.end}
          step="0.01"
          value={Math.min(cursorBounds.end, Math.max(cursorBounds.start, cursorSeconds))}
          onChange={(event) => setCursorSeconds(Number(event.target.value))}
        />
        <div className="cursor-scale" aria-hidden="true">
          <span>{formatTime(cursorBounds.start)}</span>
          <span>{formatTime(cursorBounds.end)}</span>
        </div>
      </div>
    </aside>
  );
}
