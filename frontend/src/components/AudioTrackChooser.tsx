import type { ProcessingAudioStream } from "../api/processing";

interface AudioTrackChooserProps {
  streams: ProcessingAudioStream[];
  selectedIndex: number | null;
  selectionRequired: boolean;
  busy: boolean;
  onSelect: (index: number) => void;
}

function trackDetails(stream: ProcessingAudioStream): string {
  const details = [stream.language, stream.codec];
  if (stream.sample_rate_hz !== null) {
    details.push(`${Math.round(stream.sample_rate_hz / 1000)} kHz`);
  }
  details.push(`${stream.channels ?? "?"} ch`);
  if (stream.is_default) details.push("container default");
  return details.filter(Boolean).join(" · ");
}

export function AudioTrackChooser({
  streams,
  selectedIndex,
  selectionRequired,
  busy,
  onSelect,
}: AudioTrackChooserProps) {
  if (streams.length < 2) return null;

  return (
    <fieldset className="audio-track-chooser" aria-describedby="audio-track-help">
      <legend>Choose the audio track to transcribe</legend>
      <p id="audio-track-help">
        EchoFlow found {streams.length} audio tracks in this recording. Choose the track that
        contains the evidence you want transcribed. Container titles, languages, and default
        flags are descriptive source metadata, not an EchoFlow recommendation.
      </p>
      {selectionRequired && (
        <p className="audio-track-required" role="status">
          Confirm one track before starting. EchoFlow will re-run backend preflight with that
          exact stream bound into the transcription plan.
        </p>
      )}
      <div className="audio-track-options">
        {streams.map((stream) => {
          const confirmed = !selectionRequired && selectedIndex === stream.index;
          return (
            <label
              key={stream.index}
              className={confirmed ? "audio-track-option audio-track-option-active" : "audio-track-option"}
            >
              <input
                type="radio"
                name="transcription-audio-track"
                value={stream.index}
                checked={confirmed}
                disabled={busy}
                onChange={() => onSelect(stream.index)}
              />
              <span>
                <strong>{stream.title ?? `Track #${stream.index}`}</strong>
                <small>#{stream.index} · {trackDetails(stream)}</small>
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
