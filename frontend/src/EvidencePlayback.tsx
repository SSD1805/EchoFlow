import { useEffect, useRef, useState } from "react";

import type { PlaybackClient, PlaybackSession } from "./api/playback";
import type { TranscriptGenerationRef } from "./api/transcriptTools";
import { InfoPopover } from "./components/InfoPopover";
import { formatEvidenceTime } from "./format";
import "./playback.css";

interface EvidencePlaybackProps {
  client: PlaybackClient;
  generation: TranscriptGenerationRef;
  cursorSeconds: number;
  onPositionChange: (seconds: number) => void;
}

export function EvidencePlayback({
  client,
  generation,
  cursorSeconds,
  onPositionChange,
}: EvidencePlaybackProps) {
  const mediaRef = useRef<HTMLMediaElement | null>(null);
  const [session, setSession] = useState<PlaybackSession | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    const current = session;
    return () => {
      if (current) void client.release(current.session_id);
    };
  }, [client, session]);

  useEffect(() => {
    const media = mediaRef.current;
    if (!media || !session) return;
    const bounded = Math.min(session.duration_seconds, Math.max(0, cursorSeconds));
    if (Math.abs(media.currentTime - bounded) > 0.05) {
      media.currentTime = bounded;
    }
  }, [cursorSeconds, session]);

  async function prepare() {
    setPreparing(true);
    setError(null);
    setStatus(null);
    const previous = session;
    try {
      if (previous) {
        await client.release(previous.session_id);
        setSession(null);
      }
      const prepared = await client.prepare(generation, cursorSeconds);
      setSession(prepared);
      setStatus(`Playback ready at ${formatEvidenceTime(prepared.seek_seconds)}.`);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Scholion could not prepare the original recording for playback.",
      );
    } finally {
      setPreparing(false);
    }
  }

  async function playFromCursor() {
    const media = mediaRef.current;
    if (!media || !session) return;
    media.currentTime = Math.min(session.duration_seconds, Math.max(0, cursorSeconds));
    try {
      await media.play();
    } catch {
      setError("This computer could not start playback for the recording.");
    }
  }

  function mediaError() {
    setError(
      "The recording is intact, but this computer cannot play its file format or codec.",
    );
  }

  const mediaProps = {
    src: session?.media_url,
    controls: true,
    preload: "metadata" as const,
    onLoadedMetadata: () => {
      const media = mediaRef.current;
      if (media && session) media.currentTime = session.seek_seconds;
    },
    onTimeUpdate: () => {
      const media = mediaRef.current;
      if (media && Number.isFinite(media.currentTime)) onPositionChange(media.currentTime);
    },
    onError: mediaError,
  };

  return (
    <section className="evidence-playback" aria-labelledby="evidence-playback-title">
      <div className="evidence-playback-heading">
        <div>
          <p className="mini-label">Original recording</p>
          <h3 id="evidence-playback-title">Playback</h3>
        </div>
        <div className="context-help-actions">
          <InfoPopover
            topic="playback"
            label="Why check?"
            align="end"
            className="context-help"
          />
          <button
            type="button"
            className="quiet-button"
            disabled={preparing}
            onClick={() => void prepare()}
          >
            {preparing ? "Checking…" : session ? "Check again" : "Prepare playback"}
          </button>
        </div>
      </div>

      <p className="evidence-playback-copy">
        Before playback, Scholion checks that the original recording is still the same file used for this transcript. Playback stays on this computer.
      </p>

      {status && <p className="evidence-playback-status" role="status">{status}</p>}
      {error && <p className="error-banner evidence-playback-error" role="alert">{error}</p>}

      {session && (
        <div
          className="evidence-playback-player"
          data-session-seek-seconds={session.seek_seconds}
          data-media-kind={session.media_kind}
        >
          {session.media_kind === "video" ? (
            <video
              {...mediaProps}
              ref={(node) => {
                mediaRef.current = node;
              }}
              aria-label="Original recording video"
            />
          ) : (
            <audio
              {...mediaProps}
              ref={(node) => {
                mediaRef.current = node;
              }}
              aria-label="Original recording audio"
            />
          )}
          <div className="evidence-playback-actions">
            <button type="button" className="secondary-action" onClick={() => void playFromCursor()}>
              Play from transcript position
            </button>
            <span>
              Original recording · {formatEvidenceTime(session.duration_seconds)}
            </span>
          </div>
        </div>
      )}
    </section>
  );
}
