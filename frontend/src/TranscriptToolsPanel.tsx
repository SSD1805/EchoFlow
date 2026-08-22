import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import type {
  TranscriptExportFormat,
  TranscriptGenerationRef,
  TranscriptSpeaker,
  TranscriptSpeakerSpan,
  TranscriptToolsClient,
  TranscriptToolsSnapshot,
} from "./api/transcriptTools";
import { InfoPopover } from "./components/InfoPopover";
import { formatEvidenceTime } from "./format";
import "./transcript-tools.css";

interface TranscriptToolsPanelProps {
  client: TranscriptToolsClient;
  generation: TranscriptGenerationRef;
  onClose: () => void;
}

const FORMAT_LABELS: Record<TranscriptExportFormat, string> = {
  txt: "Plain text",
  srt: "SubRip subtitles",
  vtt: "WebVTT subtitles",
};

const SPAN_LABELS: Record<TranscriptSpeakerSpan["kind"], string> = {
  "single-speaker": "Speaker",
  overlap: "Overlap",
  "mixed-unresolved": "Mixed speakers",
  unattributed: "Unattributed",
};

function speakerText(speaker: TranscriptSpeaker): string {
  return speaker.display_label
    ? `${speaker.display_label} · ${speaker.speaker_ref}`
    : speaker.speaker_ref;
}

export function TranscriptToolsPanel({
  client,
  generation,
  onClose,
}: TranscriptToolsPanelProps) {
  const [snapshot, setSnapshot] = useState<TranscriptToolsSnapshot | null>(null);
  const [spans, setSpans] = useState<TranscriptSpeakerSpan[] | null>(null);
  const [names, setNames] = useState<Record<string, string>>({});
  const [formats, setFormats] = useState<TranscriptExportFormat[]>(["txt"]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("Opening this verified transcript generation…");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setBusy(true);
    setError(null);
    void client
      .inspect(generation)
      .then((next) => {
        if (!active) return;
        setSnapshot(next);
        setNames(
          Object.fromEntries(
            next.speakers.map((speaker) => [speaker.speaker_ref, speaker.display_label ?? ""]),
          ),
        );
        setStatus("Transcript tools are ready for this verified generation.");
      })
      .catch((caught) => {
        if (!active) return;
        setError(
          caught instanceof Error ? caught.message : "Scholion could not open transcript tools.",
        );
        setStatus("Transcript tools could not be opened.");
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, [client, generation]);

  function replaceSpeaker(next: TranscriptSpeaker) {
    setSnapshot((current) =>
      current
        ? {
            ...current,
            speakers: current.speakers.map((speaker) =>
              speaker.speaker_ref === next.speaker_ref ? next : speaker,
            ),
          }
        : current,
    );
    setNames((current) => ({
      ...current,
      [next.speaker_ref]: next.display_label ?? "",
    }));
    setSpans(null);
  }

  async function saveName(event: FormEvent<HTMLFormElement>, speakerRef: string) {
    event.preventDefault();
    const label = names[speakerRef]?.trim() ?? "";
    if (!label) {
      setError("Enter a speaker name before saving it.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const next = await client.setSpeakerLabel(generation, speakerRef, label);
      replaceSpeaker(next);
      setStatus(`${speakerRef} is now shown as ${next.display_label}.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Scholion could not save that name.");
    } finally {
      setBusy(false);
    }
  }

  async function removeName(speakerRef: string) {
    setBusy(true);
    setError(null);
    try {
      await client.removeSpeakerLabel(generation, speakerRef);
      replaceSpeaker({
        speaker_ref: speakerRef,
        display_label: null,
        display_name: speakerRef,
      });
      setStatus(`Removed the display name for ${speakerRef}. The anonymous evidence ref remains.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Scholion could not remove that name.");
    } finally {
      setBusy(false);
    }
  }

  async function loadSpans() {
    setBusy(true);
    setError(null);
    try {
      const next = await client.speakerSpans(generation);
      setSpans(next);
      setStatus(`Opened ${next.length} speaker-aware transcript span${next.length === 1 ? "" : "s"}.`);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Scholion could not open the speaker transcript.",
      );
    } finally {
      setBusy(false);
    }
  }

  function toggleFormat(format: TranscriptExportFormat) {
    setFormats((current) =>
      current.includes(format)
        ? current.filter((candidate) => candidate !== format)
        : [...current, format],
    );
  }

  async function publish() {
    if (formats.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const destination = await client.chooseDestinationFolder();
      if (destination === null) {
        setStatus("Publication cancelled. No transcript export was created.");
        return;
      }
      const result = await client.publish(generation, destination, formats);
      const filenames = result.publications.map((item) => item.filename).join(", ");
      setStatus(`Published ${result.publications.length} file${result.publications.length === 1 ? "" : "s"}: ${filenames}.`);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Scholion could not publish those transcript views.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="transcript-tools" aria-labelledby="transcript-tools-title">
      <header className="transcript-tools-header">
        <div>
          <p className="mini-label">Transcript</p>
          <h2 id="transcript-tools-title">Transcript tools</h2>
        </div>
        <div className="context-help-actions">
          <InfoPopover
            topic="transcript-tools"
            label="How these work"
            align="end"
            className="context-help"
          />
          <button type="button" className="quiet-button" onClick={onClose}>
            Close
          </button>
        </div>
      </header>

      <p className="transcript-tools-status" role="status">{status}</p>
      {error && <p className="error-banner" role="alert">{error}</p>}

      {snapshot && (
        <>
          <section className="transcript-summary" aria-labelledby="transcript-summary-title">
            <div>
              <p className="mini-label">Current verified generation</p>
              <h3 id="transcript-summary-title">{snapshot.details.document_id}</h3>
            </div>
            <dl className="transcript-summary-grid">
              <div><dt>Duration</dt><dd>{formatEvidenceTime(snapshot.details.duration_seconds)}</dd></div>
              <div><dt>Language</dt><dd>{snapshot.details.detected_languages.join(", ") || "Unknown"}</dd></div>
              <div><dt>Segments</dt><dd>{snapshot.details.segment_count}</dd></div>
              <div><dt>Speakers</dt><dd>{snapshot.details.speaker_count}</dd></div>
              <div><dt>Source recording</dt><dd>{snapshot.details.source_available ? "Available locally" : "Not currently available"}</dd></div>
              <div><dt>Canonical generation</dt><dd><code>{snapshot.details.canonical_sha256.slice(0, 12)}…</code></dd></div>
            </dl>
          </section>

          <section className="speaker-tools" aria-labelledby="speaker-tools-title">
            <div className="transcript-section-heading">
              <div>
                <p className="mini-label">People</p>
                <h3 id="speaker-tools-title">Name anonymous speakers</h3>
              </div>
              <button type="button" className="secondary-action" disabled={busy} onClick={() => void loadSpans()}>
                Open speaker transcript
              </button>
            </div>
            <p className="transcript-tools-explainer">
              Names are your private labels. Scholion keeps the anonymous speaker reference beside them as evidence.
            </p>
            <div className="speaker-roster">
              {snapshot.speakers.length === 0 ? (
                <p>No anonymous speaker evidence is present in this transcript.</p>
              ) : (
                snapshot.speakers.map((speaker) => (
                  <form
                    className="speaker-row"
                    key={speaker.speaker_ref}
                    aria-label={`Speaker ${speaker.speaker_ref}`}
                    onSubmit={(event) => void saveName(event, speaker.speaker_ref)}
                  >
                    <div className="speaker-identity">
                      <strong>{speakerText(speaker)}</strong>
                      <code>{speaker.speaker_ref}</code>
                    </div>
                    <label>
                      <span>Display name</span>
                      <input
                        value={names[speaker.speaker_ref] ?? ""}
                        maxLength={200}
                        aria-label={`Display name for ${speaker.speaker_ref}`}
                        onChange={(event) =>
                          setNames((current) => ({
                            ...current,
                            [speaker.speaker_ref]: event.target.value,
                          }))
                        }
                      />
                    </label>
                    <div className="speaker-actions">
                      <button type="submit" className="secondary-action" disabled={busy}>
                        Save name
                      </button>
                      {speaker.display_label && (
                        <button type="button" className="quiet-button" disabled={busy} onClick={() => void removeName(speaker.speaker_ref)}>
                          Remove name
                        </button>
                      )}
                    </div>
                  </form>
                ))
              )}
            </div>
          </section>

          {spans && (
            <section className="speaker-transcript" aria-labelledby="speaker-transcript-title">
              <div className="transcript-section-heading">
                <div>
                  <p className="mini-label">Derived reading view</p>
                  <h3 id="speaker-transcript-title">Speaker transcript</h3>
                </div>
                <button type="button" className="quiet-button" onClick={() => setSpans(null)}>Hide</button>
              </div>
              <div className="speaker-span-list">
                {spans.map((span) => (
                  <article className="speaker-span" data-kind={span.kind} key={`${span.segment_id}:${span.start_seconds}`}>
                    <div className="speaker-span-meta">
                      <time dateTime={`PT${span.start_seconds}S`}>{formatEvidenceTime(span.start_seconds)}</time>
                      <strong>{SPAN_LABELS[span.kind]}</strong>
                      <span>{span.speakers.map((speaker) => speaker.display_name).join(" + ") || "No speaker attributed"}</span>
                    </div>
                    <p>{span.text}</p>
                  </article>
                ))}
              </div>
            </section>
          )}

          <section className="publication-tools" aria-labelledby="publication-tools-title">
            <p className="mini-label">Derived files</p>
            <h3 id="publication-tools-title">Publish a transcript copy</h3>
            <p className="transcript-tools-explainer">
              These are disposable views of the verified canonical transcript. Publishing does not change the evidence underneath them.
            </p>
            <fieldset>
              <legend>Formats</legend>
              {(Object.keys(FORMAT_LABELS) as TranscriptExportFormat[]).map((format) => (
                <label key={format}>
                  <input
                    type="checkbox"
                    checked={formats.includes(format)}
                    onChange={() => toggleFormat(format)}
                  />
                  <span>{FORMAT_LABELS[format]}</span>
                </label>
              ))}
            </fieldset>
            <button type="button" className="primary-action" disabled={busy || formats.length === 0} onClick={() => void publish()}>
              Choose folder and publish
            </button>
          </section>

          <details className="transcript-technical-details">
            <summary>Technical details</summary>
            <dl>
              <div><dt>Engine</dt><dd>{snapshot.details.engine.name} {snapshot.details.engine.package_version}</dd></div>
              <div><dt>Model</dt><dd>{snapshot.details.engine.model}</dd></div>
              <div><dt>Model revision</dt><dd><code>{snapshot.details.engine.model_revision}</code></dd></div>
              <div><dt>Execution</dt><dd>{snapshot.details.engine.device} / {snapshot.details.engine.compute_type}</dd></div>
              <div><dt>Audio stream</dt><dd>#{snapshot.details.audio_stream_index}</dd></div>
              <div><dt>Decode</dt><dd>{snapshot.details.decode_strategy}</dd></div>
              <div><dt>Profile</dt><dd>{snapshot.details.profile}{snapshot.details.provisional ? " · provisional" : ""}</dd></div>
              <div><dt>Diarization</dt><dd>{snapshot.details.diarization ? `${snapshot.details.diarization.provider} ${snapshot.details.diarization.package_version}` : "Not used"}</dd></div>
              <div><dt>Enhancement</dt><dd>{snapshot.details.enhancement?.provider ?? "Not used"}</dd></div>
            </dl>
          </details>
        </>
      )}
    </aside>
  );
}
