import type {
  WorkspaceContextSegment,
  WorkspaceEvidenceResult,
  WorkspaceMatchedWord,
} from "./api/desktop";
import { formatEvidenceTime } from "./format";
import "./evidence-reader.css";

interface EvidenceReaderProps {
  evidence: WorkspaceEvidenceResult;
  onClose: () => void;
}

function wordSeparator(current: WorkspaceMatchedWord, next: WorkspaceMatchedWord | undefined) {
  if (!next) return "";
  if (/\s$/.test(current.text) || /^\s/.test(next.text)) return "";
  if (/^[,.;:!?%)\]}]/.test(next.text)) return "";
  return " ";
}

function renderWords(segment: WorkspaceContextSegment) {
  if (segment.words.length === 0) {
    return segment.text;
  }
  return segment.words.map((word, index) => {
    const content = word.highlighted ? (
      <mark
        key={`${word.segment_id}:${word.word_index}`}
        data-word-index={word.word_index}
        data-word-start={word.start_seconds}
      >
        {word.text}
      </mark>
    ) : (
      <span key={`${word.segment_id}:${word.word_index}`}>{word.text}</span>
    );
    return (
      <span key={`word-wrap:${word.segment_id}:${word.word_index}`}>
        {content}
        {wordSeparator(word, segment.words[index + 1])}
      </span>
    );
  });
}

export function EvidenceReader({ evidence, onClose }: EvidenceReaderProps) {
  return (
    <aside className="evidence-reader" aria-labelledby="evidence-reader-title">
      <header className="evidence-reader-header">
        <div>
          <p className="mini-label">Verified canonical window</p>
          <h2 id="evidence-reader-title">Evidence reader</h2>
        </div>
        <button type="button" className="quiet-button" onClick={onClose}>
          Close
        </button>
      </header>

      <dl className="evidence-proof">
        <div>
          <dt>Transcript</dt>
          <dd>{evidence.document_id}</dd>
        </div>
        <div>
          <dt>Canonical generation</dt>
          <dd>
            <code>{evidence.canonical_sha256.slice(0, 12)}…</code>
          </dd>
        </div>
        <div>
          <dt>Verified span</dt>
          <dd>
            {formatEvidenceTime(evidence.start_seconds)}–{formatEvidenceTime(evidence.end_seconds)}
          </dd>
        </div>
      </dl>

      <div className="evidence-context" aria-label="Verified transcript context">
        {evidence.context_segments.length === 0 ? (
          <section className="context-segment result-segment">
            <div className="context-meta">
              <time dateTime={`PT${evidence.start_seconds}S`}>
                {formatEvidenceTime(evidence.start_seconds)}
              </time>
              <span>Search result</span>
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
                <span>{segment.is_result_segment ? "Search result" : "Context"}</span>
                {segment.speaker_refs.length > 0 && (
                  <span>{segment.speaker_refs.join(", ")}</span>
                )}
              </div>
              <p>{renderWords(segment)}</p>
            </section>
          ))
        )}
      </div>

      <footer className="evidence-seek" data-seek-seconds={evidence.seek_seconds}>
        <div>
          <span className="mini-label">Verified seek point</span>
          <strong>{formatEvidenceTime(evidence.seek_seconds)}</strong>
        </div>
        <p>
          This source-relative coordinate is verified against canonical evidence. Media
          playback can consume it without exposing source or canonical filesystem paths to
          the webview.
        </p>
      </footer>
    </aside>
  );
}
