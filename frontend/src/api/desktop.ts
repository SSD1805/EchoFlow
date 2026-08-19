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
}

export function createDesktopClient(): DesktopClient {
  const params = new URLSearchParams(window.location.search);
  return params.get("e2e") === "1" ? new MockDesktopClient() : new TauriDesktopClient();
}
