export type LocationKind = "recording-source" | "transcript-library";
export type ProcessingPolicy = "manual" | "automatic";

export interface LibraryLocation {
  location_id: string;
  path: string;
  kind: LocationKind;
  enabled: boolean;
  processing_policy: ProcessingPolicy;
  created_at: string;
  updated_at: string;
}

export interface DiscoveredRecording {
  path: string;
  size_bytes: number;
  location_ids: string[];
  automatic_processing_requested: boolean;
}

export interface RecordingDiscoveryReport {
  recordings: DiscoveredRecording[];
  unavailable_location_ids: string[];
}

export interface WorkspaceSpeaker {
  speaker_ref: string;
  display_label: string | null;
}

export interface WorkspaceMatchedWord {
  segment_id: string;
  word_index: number;
  start_seconds: number;
  end_seconds: number;
  text: string;
  speaker_ref: string | null;
}

export interface WorkspaceEvidenceResult {
  document_id: string;
  source_sha256: string;
  canonical_sha256: string;
  segment_ids: string[];
  text: string;
  start_seconds: number;
  end_seconds: number;
  seek_seconds: number;
  languages: string[];
  speakers: WorkspaceSpeaker[];
  matched_words: WorkspaceMatchedWord[];
  note_count: number;
  tags: string[];
  collections: string[];
}

export interface WorkspaceNoteResult {
  note_id: string;
  body: string;
  document_id: string;
  canonical_sha256: string;
  segment_ids: string[];
  start_seconds: number;
  end_seconds: number;
  current: boolean;
  tags: string[];
  collections: string[];
}

export interface WorkspaceNamedResult {
  name: string;
}

export interface WorkspaceTagResult extends WorkspaceNamedResult {
  tag_id: string;
}

export interface WorkspaceCollectionResult extends WorkspaceNamedResult {
  collection_id: string;
}

export interface WorkspaceDiscoveryReport {
  query: string;
  total_count: number;
  evidence: WorkspaceEvidenceResult[];
  notes: WorkspaceNoteResult[];
  tags: WorkspaceTagResult[];
  collections: WorkspaceCollectionResult[];
}

interface DesktopError {
  code: string;
  message: string;
}

interface DesktopResponse<T> {
  protocol_version: 1;
  request_id: string;
  ok: boolean;
  result: T | null;
  error: DesktopError | null;
}

export interface DesktopClient {
  chooseFiles(kind: LocationKind): Promise<string[]>;
  chooseFolder(): Promise<string | null>;
  listLocations(): Promise<LibraryLocation[]>;
  rememberLocation(
    path: string,
    kind: LocationKind,
    processingPolicy: ProcessingPolicy,
  ): Promise<LibraryLocation>;
  discoverRecordings(): Promise<RecordingDiscoveryReport>;
  refreshTranscriptLocations(): Promise<void>;
  discoverWorkspace(text: string): Promise<WorkspaceDiscoveryReport>;
}

function assertResponse<T>(value: unknown): DesktopResponse<T> {
  if (!value || typeof value !== "object") {
    throw new Error("EchoFlow desktop bridge returned an invalid response");
  }
  const candidate = value as Partial<DesktopResponse<T>>;
  if (
    candidate.protocol_version !== 1 ||
    typeof candidate.request_id !== "string" ||
    typeof candidate.ok !== "boolean"
  ) {
    throw new Error("EchoFlow desktop bridge returned an incompatible response");
  }
  return candidate as DesktopResponse<T>;
}

class TauriDesktopClient implements DesktopClient {
  private async request<T>(method: string, params: Record<string, unknown>): Promise<T> {
    const { invoke } = await import("@tauri-apps/api/core");
    const request = {
      protocol_version: 1,
      request_id: crypto.randomUUID(),
      method,
      params,
    };
    const response = assertResponse<T>(
      await invoke<unknown>("desktop_request", { request }),
    );
    if (!response.ok || response.result === null) {
      throw new Error(response.error?.message ?? "EchoFlow could not complete that request");
    }
    return response.result;
  }

  async chooseFiles(kind: LocationKind): Promise<string[]> {
    const { open } = await import("@tauri-apps/plugin-dialog");
    const filters =
      kind === "transcript-library"
        ? [{ name: "EchoFlow transcript", extensions: ["json"] }]
        : [
            {
              name: "Audio and video",
              extensions: [
                "aac",
                "aiff",
                "avi",
                "flac",
                "m4a",
                "m4v",
                "mkv",
                "mov",
                "mp3",
                "mp4",
                "mpeg",
                "mpg",
                "ogg",
                "opus",
                "wav",
                "webm",
                "wma",
              ],
            },
          ];
    const selected = await open({ multiple: true, directory: false, filters });
    if (!selected) return [];
    return Array.isArray(selected) ? selected : [selected];
  }

  async chooseFolder(): Promise<string | null> {
    const { open } = await import("@tauri-apps/plugin-dialog");
    const selected = await open({ multiple: false, directory: true });
    return typeof selected === "string" ? selected : null;
  }

  listLocations(): Promise<LibraryLocation[]> {
    return this.request("locations.list", {});
  }

  rememberLocation(
    path: string,
    kind: LocationKind,
    processingPolicy: ProcessingPolicy,
  ): Promise<LibraryLocation> {
    return this.request("locations.add", {
      path,
      kind,
      processing_policy: processingPolicy,
    });
  }

  discoverRecordings(): Promise<RecordingDiscoveryReport> {
    return this.request("recordings.discover", {});
  }

  async refreshTranscriptLocations(): Promise<void> {
    await this.request("transcripts.refresh", { verify: false });
  }

  discoverWorkspace(text: string): Promise<WorkspaceDiscoveryReport> {
    return this.request("workspace.discover", {
      text,
      limit: 20,
      context_segments: 1,
    });
  }
}

class MockDesktopClient implements DesktopClient {
  private locations: LibraryLocation[] = [];

  async chooseFiles(kind: LocationKind): Promise<string[]> {
    return kind === "transcript-library"
      ? ["/Users/susan/Research/interview-01.echoflow.json"]
      : [
          "/Users/susan/Research/interview-01.m4a",
          "/Users/susan/Research/interview-02.mp4",
        ];
  }

  async chooseFolder(): Promise<string> {
    return "/Users/susan/Research/Oral Histories";
  }

  async listLocations(): Promise<LibraryLocation[]> {
    return [...this.locations];
  }

  async rememberLocation(
    path: string,
    kind: LocationKind,
    processingPolicy: ProcessingPolicy,
  ): Promise<LibraryLocation> {
    const now = "2026-08-19T19:20:00+00:00";
    const location: LibraryLocation = {
      location_id: `location-${this.locations.length + 1}`,
      path,
      kind,
      enabled: true,
      processing_policy: processingPolicy,
      created_at: now,
      updated_at: now,
    };
    this.locations.push(location);
    return location;
  }

  async discoverRecordings(): Promise<RecordingDiscoveryReport> {
    return {
      recordings: [
        {
          path: "/Users/susan/Research/Oral Histories/interview-01.m4a",
          size_bytes: 48_391_232,
          location_ids: this.locations.map((item) => item.location_id),
          automatic_processing_requested: this.locations.some(
            (item) => item.processing_policy === "automatic",
          ),
        },
        {
          path: "/Users/susan/Research/Oral Histories/interview-02.mp4",
          size_bytes: 802_160_640,
          location_ids: this.locations.map((item) => item.location_id),
          automatic_processing_requested: this.locations.some(
            (item) => item.processing_policy === "automatic",
          ),
        },
      ],
      unavailable_location_ids: [],
    };
  }

  async refreshTranscriptLocations(): Promise<void> {
    return Promise.resolve();
  }

  async discoverWorkspace(text: string): Promise<WorkspaceDiscoveryReport> {
    const query = text.trim();
    if (!query) throw new Error("Search text cannot be empty");
    return {
      query,
      total_count: 4,
      evidence: [
        {
          document_id: "interview-42",
          source_sha256: "b".repeat(64),
          canonical_sha256: "a".repeat(64),
          segment_ids: ["segment-17"],
          text: `We started the ${query} program after the second interview round.`,
          start_seconds: 862.1,
          end_seconds: 870.4,
          seek_seconds: 862.43,
          languages: ["en"],
          speakers: [{ speaker_ref: "speaker-1", display_label: "Participant A" }],
          matched_words: [
            {
              segment_id: "segment-17",
              word_index: 3,
              start_seconds: 862.43,
              end_seconds: 862.72,
              text: query,
              speaker_ref: "speaker-1",
            },
          ],
          note_count: 1,
          tags: ["program"],
          collections: ["Oral histories"],
        },
      ],
      notes: [
        {
          note_id: "note-7",
          body: `Follow up on ${query} governance during the next interview.`,
          document_id: "interview-42",
          canonical_sha256: "a".repeat(64),
          segment_ids: ["segment-17"],
          start_seconds: 862.1,
          end_seconds: 870.4,
          current: true,
          tags: ["program"],
          collections: ["Oral histories"],
        },
      ],
      tags: [{ tag_id: "tag-3", name: "program" }],
      collections: [{ collection_id: "collection-2", name: "Oral histories" }],
    };
  }
}

export function createDesktopClient(): DesktopClient {
  const params = new URLSearchParams(window.location.search);
  return params.get("e2e") === "1" ? new MockDesktopClient() : new TauriDesktopClient();
}
