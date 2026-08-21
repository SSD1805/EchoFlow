export type TranscriptExportFormat = "txt" | "srt" | "vtt";
export type SpeakerPresentationKind =
  | "single-speaker"
  | "overlap"
  | "mixed-unresolved"
  | "unattributed";

export interface TranscriptGenerationRef {
  document_id: string;
  canonical_sha256: string;
}

export interface TranscriptSpeaker {
  speaker_ref: string;
  display_label: string | null;
  display_name: string;
}

export interface TranscriptEngineDetails {
  name: string;
  package_version: string;
  model: string;
  model_revision: string;
  device: string;
  compute_type: string;
}

export interface TranscriptDiarizationDetails {
  provider: string;
  package_version: string;
  model: string;
  model_revision: string | null;
  mode: string;
}

export interface TranscriptEnhancementDetails {
  provider: string;
  provider_version: string;
  operation: string;
  model_id: string | null;
  model_revision: string | null;
}

export interface TranscriptDetails extends TranscriptGenerationRef {
  source_sha256: string;
  source_available: boolean;
  source_size_bytes: number;
  source_modified_ns: number;
  container_format: string;
  duration_seconds: number;
  audio_stream_index: number;
  profile: string;
  provisional: boolean;
  decode_strategy: string;
  detected_language: string | null;
  detected_languages: string[];
  segment_count: number;
  speaker_count: number;
  engine: TranscriptEngineDetails;
  diarization: TranscriptDiarizationDetails | null;
  enhancement: TranscriptEnhancementDetails | null;
}

export interface TranscriptToolsSnapshot {
  details: TranscriptDetails;
  speakers: TranscriptSpeaker[];
}

export interface PresentedSpeaker {
  speaker_ref: string;
  display_label: string | null;
  display_name: string;
}

export interface TranscriptSpeakerSpan {
  document_id: string;
  canonical_sha256: string;
  segment_id: string;
  start_seconds: number;
  end_seconds: number;
  text: string;
  kind: SpeakerPresentationKind;
  overlap: boolean;
  speakers: PresentedSpeaker[];
}

export interface TranscriptPublication {
  format: TranscriptExportFormat;
  filename: string;
}

export interface TranscriptPublishResult {
  canonical_sha256: string;
  publications: TranscriptPublication[];
}

interface TranscriptToolsError {
  code: string;
  message: string;
}

interface TranscriptToolsResponse<T> {
  protocol_version: 1;
  request_id: string;
  ok: boolean;
  result: T | null;
  error: TranscriptToolsError | null;
}

export interface TranscriptToolsClient {
  inspect(ref: TranscriptGenerationRef): Promise<TranscriptToolsSnapshot>;
  speakerSpans(ref: TranscriptGenerationRef): Promise<TranscriptSpeakerSpan[]>;
  setSpeakerLabel(
    ref: TranscriptGenerationRef,
    speakerRef: string,
    label: string,
  ): Promise<TranscriptSpeaker>;
  removeSpeakerLabel(ref: TranscriptGenerationRef, speakerRef: string): Promise<boolean>;
  chooseDestinationFolder(): Promise<string | null>;
  publish(
    ref: TranscriptGenerationRef,
    destination: string,
    formats: TranscriptExportFormat[],
  ): Promise<TranscriptPublishResult>;
}

function assertResponse<T>(value: unknown): TranscriptToolsResponse<T> {
  if (!value || typeof value !== "object") {
    throw new Error("EchoFlow transcript tools returned an invalid response");
  }
  const candidate = value as Partial<TranscriptToolsResponse<T>>;
  if (
    candidate.protocol_version !== 1 ||
    typeof candidate.request_id !== "string" ||
    typeof candidate.ok !== "boolean"
  ) {
    throw new Error("EchoFlow transcript tools returned an incompatible response");
  }
  return candidate as TranscriptToolsResponse<T>;
}

class TauriTranscriptToolsClient implements TranscriptToolsClient {
  private async request<T>(method: string, params: Record<string, unknown>): Promise<T> {
    const { invoke } = await import("@tauri-apps/api/core");
    const request = {
      protocol_version: 1,
      request_id: crypto.randomUUID(),
      method,
      params,
    };
    const response = assertResponse<T>(
      await invoke<unknown>("transcript_tools_request", { request }),
    );
    if (!response.ok || response.result === null) {
      throw new Error(
        response.error?.message ?? "EchoFlow could not complete that transcript-tools request",
      );
    }
    return response.result;
  }

  inspect(ref: TranscriptGenerationRef): Promise<TranscriptToolsSnapshot> {
    return this.request("transcripts.tools.inspect", ref);
  }

  async speakerSpans(ref: TranscriptGenerationRef): Promise<TranscriptSpeakerSpan[]> {
    const result = await this.request<{ spans: TranscriptSpeakerSpan[] }>(
      "transcripts.tools.speakers",
      ref,
    );
    return result.spans;
  }

  setSpeakerLabel(
    ref: TranscriptGenerationRef,
    speakerRef: string,
    label: string,
  ): Promise<TranscriptSpeaker> {
    return this.request("transcripts.tools.speaker.set", {
      ...ref,
      speaker_ref: speakerRef,
      label,
    });
  }

  async removeSpeakerLabel(
    ref: TranscriptGenerationRef,
    speakerRef: string,
  ): Promise<boolean> {
    const result = await this.request<{ removed: boolean }>(
      "transcripts.tools.speaker.remove",
      { ...ref, speaker_ref: speakerRef },
    );
    return result.removed;
  }

  async chooseDestinationFolder(): Promise<string | null> {
    const { open } = await import("@tauri-apps/plugin-dialog");
    const selected = await open({ multiple: false, directory: true });
    return typeof selected === "string" ? selected : null;
  }

  publish(
    ref: TranscriptGenerationRef,
    destination: string,
    formats: TranscriptExportFormat[],
  ): Promise<TranscriptPublishResult> {
    return this.request("transcripts.tools.publish", {
      ...ref,
      destination,
      formats,
    });
  }
}

const MOCK_GENERATION: TranscriptGenerationRef = {
  document_id: "interview-42",
  canonical_sha256: "a".repeat(64),
};

function sameGeneration(ref: TranscriptGenerationRef): boolean {
  return (
    ref.document_id === MOCK_GENERATION.document_id &&
    ref.canonical_sha256 === MOCK_GENERATION.canonical_sha256
  );
}

class MockTranscriptToolsClient implements TranscriptToolsClient {
  private labels = new Map<string, string>([["speaker-1", "Participant A"]]);

  private requireGeneration(ref: TranscriptGenerationRef): void {
    if (!sameGeneration(ref)) {
      throw new Error("Transcript generation changed; reopen transcript tools before editing");
    }
  }

  private speaker(speakerRef: string): TranscriptSpeaker {
    const displayLabel = this.labels.get(speakerRef) ?? null;
    return {
      speaker_ref: speakerRef,
      display_label: displayLabel,
      display_name: displayLabel ? `${displayLabel} (${speakerRef})` : speakerRef,
    };
  }

  async inspect(ref: TranscriptGenerationRef): Promise<TranscriptToolsSnapshot> {
    this.requireGeneration(ref);
    return {
      details: {
        ...MOCK_GENERATION,
        source_sha256: "b".repeat(64),
        source_available: true,
        source_size_bytes: 48_391_232,
        source_modified_ns: 1,
        container_format: "m4a",
        duration_seconds: 1460.4,
        audio_stream_index: 0,
        profile: "balanced",
        provisional: false,
        decode_strategy: "direct",
        detected_language: "en",
        detected_languages: ["en"],
        segment_count: 128,
        speaker_count: 2,
        engine: {
          name: "faster-whisper",
          package_version: "1.2.1",
          model: "small",
          model_revision: "mock-small-revision",
          device: "cpu",
          compute_type: "int8",
        },
        diarization: {
          provider: "pyannote.audio",
          package_version: "4.0.0",
          model: "speaker-diarization-community-1",
          model_revision: "mock-diarization-revision",
          mode: "anonymous_turns_v1",
        },
        enhancement: null,
      },
      speakers: [this.speaker("speaker-1"), this.speaker("speaker-2")],
    };
  }

  async speakerSpans(ref: TranscriptGenerationRef): Promise<TranscriptSpeakerSpan[]> {
    this.requireGeneration(ref);
    return [
      {
        ...MOCK_GENERATION,
        segment_id: "segment-17",
        start_seconds: 862.1,
        end_seconds: 864.4,
        text: "We started the program.",
        kind: "single-speaker",
        overlap: false,
        speakers: [this.speaker("speaker-1")],
      },
      {
        ...MOCK_GENERATION,
        segment_id: "segment-18",
        start_seconds: 864.4,
        end_seconds: 865.8,
        text: "Yes, exactly.",
        kind: "overlap",
        overlap: true,
        speakers: [this.speaker("speaker-1"), this.speaker("speaker-2")],
      },
    ];
  }

  async setSpeakerLabel(
    ref: TranscriptGenerationRef,
    speakerRef: string,
    label: string,
  ): Promise<TranscriptSpeaker> {
    this.requireGeneration(ref);
    const normalized = label.trim();
    if (!normalized) throw new Error("Speaker name cannot be blank");
    if (!["speaker-1", "speaker-2"].includes(speakerRef)) {
      throw new Error("Speaker is not present in this transcript generation");
    }
    this.labels.set(speakerRef, normalized);
    return this.speaker(speakerRef);
  }

  async removeSpeakerLabel(
    ref: TranscriptGenerationRef,
    speakerRef: string,
  ): Promise<boolean> {
    this.requireGeneration(ref);
    return this.labels.delete(speakerRef);
  }

  async chooseDestinationFolder(): Promise<string> {
    return "/Users/susan/Research/Exports";
  }

  async publish(
    ref: TranscriptGenerationRef,
    _destination: string,
    formats: TranscriptExportFormat[],
  ): Promise<TranscriptPublishResult> {
    this.requireGeneration(ref);
    const unique = [...new Set(formats)];
    if (unique.length === 0 || unique.length > 3) {
      throw new Error("Choose between one and three transcript formats");
    }
    return {
      canonical_sha256: ref.canonical_sha256,
      publications: unique.map((format) => ({
        format,
        filename: `${ref.document_id}.${format}`,
      })),
    };
  }
}

export function createTranscriptToolsClient(): TranscriptToolsClient {
  const params = new URLSearchParams(window.location.search);
  return params.get("e2e") === "1"
    ? new MockTranscriptToolsClient()
    : new TauriTranscriptToolsClient();
}
