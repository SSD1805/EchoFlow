import type { TranscriptGenerationRef } from "./transcriptTools";

export type PlaybackMediaKind = "audio" | "video";

export interface PlaybackSession {
  session_id: string;
  media_url: string;
  duration_seconds: number;
  seek_seconds: number;
  media_kind: PlaybackMediaKind;
}

interface NativePlaybackPrepared {
  session_id: string;
  media_token: string;
  duration_seconds: number;
  seek_seconds: number;
  media_kind: PlaybackMediaKind;
}

interface NativePlaybackReleased {
  released: boolean;
}

export interface PlaybackClient {
  prepare(ref: TranscriptGenerationRef, seekSeconds: number): Promise<PlaybackSession>;
  release(sessionId: string): Promise<boolean>;
}

function assertPrepared(value: unknown): NativePlaybackPrepared {
  if (!value || typeof value !== "object") {
    throw new Error("EchoFlow playback returned an invalid native session");
  }
  const candidate = value as Partial<NativePlaybackPrepared>;
  if (
    typeof candidate.session_id !== "string" ||
    typeof candidate.media_token !== "string" ||
    typeof candidate.duration_seconds !== "number" ||
    !Number.isFinite(candidate.duration_seconds) ||
    candidate.duration_seconds <= 0 ||
    typeof candidate.seek_seconds !== "number" ||
    !Number.isFinite(candidate.seek_seconds) ||
    candidate.seek_seconds < 0 ||
    candidate.seek_seconds > candidate.duration_seconds ||
    (candidate.media_kind !== "audio" && candidate.media_kind !== "video")
  ) {
    throw new Error("EchoFlow playback returned an incompatible native session");
  }
  return candidate as NativePlaybackPrepared;
}

class TauriPlaybackClient implements PlaybackClient {
  async prepare(
    ref: TranscriptGenerationRef,
    seekSeconds: number,
  ): Promise<PlaybackSession> {
    const { convertFileSrc, invoke } = await import("@tauri-apps/api/core");
    const prepared = assertPrepared(
      await invoke<unknown>("playback_prepare", {
        request: {
          document_id: ref.document_id,
          canonical_sha256: ref.canonical_sha256,
          seek_seconds: seekSeconds,
        },
      }),
    );
    return {
      session_id: prepared.session_id,
      media_url: convertFileSrc(prepared.media_token, "echoflow-media"),
      duration_seconds: prepared.duration_seconds,
      seek_seconds: prepared.seek_seconds,
      media_kind: prepared.media_kind,
    };
  }

  async release(sessionId: string): Promise<boolean> {
    const { invoke } = await import("@tauri-apps/api/core");
    const released = await invoke<NativePlaybackReleased>("playback_release", {
      sessionId,
    });
    return released.released;
  }
}

class MockPlaybackClient implements PlaybackClient {
  private nextId = 1;

  async prepare(
    ref: TranscriptGenerationRef,
    seekSeconds: number,
  ): Promise<PlaybackSession> {
    const params = new URLSearchParams(window.location.search);
    const failure = params.get("playback");
    if (failure === "missing") {
      throw new Error("Original recording is unavailable at its recorded location");
    }
    if (failure === "changed") {
      throw new Error("Original recording no longer matches the source used for this transcript");
    }
    if (failure === "multi-audio") {
      throw new Error(
        "Playback for recordings with multiple audio streams is not enabled yet; EchoFlow will not guess which track matches this transcript",
      );
    }
    if (!Number.isFinite(seekSeconds) || seekSeconds < 0 || seekSeconds > 1460.4) {
      throw new Error("Playback position is outside the verified recording duration");
    }
    const sessionId = `e2e-playback-${this.nextId++}`;
    return {
      session_id: sessionId,
      media_url: `mock-media://${sessionId}`,
      duration_seconds: 1460.4,
      seek_seconds: seekSeconds,
      media_kind: params.get("media") === "video" ? "video" : "audio",
    };
  }

  async release(_sessionId: string): Promise<boolean> {
    return true;
  }
}

export function createPlaybackClient(): PlaybackClient {
  const params = new URLSearchParams(window.location.search);
  return params.get("e2e") === "1" ? new MockPlaybackClient() : new TauriPlaybackClient();
}
