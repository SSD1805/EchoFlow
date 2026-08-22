import { invokeNativeProtocol } from "./nativeProtocol";

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
  highlighted: boolean;
}

export interface WorkspaceContextSegment {
  segment_id: string;
  start_seconds: number;
  end_seconds: number;
  text: string;
  speaker_refs: string[];
  words: WorkspaceMatchedWord[];
  is_result_segment: boolean;
  lexical_match: boolean;
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
  context_segments: WorkspaceContextSegment[];
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

export interface ResearchNoteResult extends WorkspaceNoteResult {
  created_at: string;
  updated_at: string;
}

export interface ResearchNoteUpdate {
  body: string;
  tags: string[];
  collections: string[];
}

export interface ResearchNoteEvidenceResult {
  note_id: string;
  current: boolean;
  evidence: WorkspaceEvidenceResult;
}

export interface ResearchNoteFilterResult {
  tags: string[];
  collections: string[];
  notes: ResearchNoteResult[];
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

export interface ResearchOverview {
  notes: ResearchNoteResult[];
  tags: WorkspaceTagResult[];
  collections: WorkspaceCollectionResult[];
}

export type ResearchSearchOperator = "any" | "all";
export type ResearchSearchSort = "relevance" | "timeline";
export type ResearchRetrievalMode = "lexical" | "semantic" | "hybrid";

export interface ResearchSearchIntent {
  query_text: string;
  phrase: boolean;
  operator: ResearchSearchOperator;
  speaker_refs: string[];
  languages: string[];
  document_ids: string[];
  sort: ResearchSearchSort;
  limit: number;
  retrieval_mode: ResearchRetrievalMode;
  context_segments: number;
  tags: string[];
  collections: string[];
  note_text: string | null;
  with_notes: boolean;
}

export interface ResearchSearchRetrievalState {
  mode: ResearchRetrievalMode;
  lexical_backend_id: string | null;
  semantic_backend_id: string | null;
  fusion_profile: string | null;
  semantic_profile: {
    model_id: string;
    resolved_revision: string;
    dimensions: number;
  } | null;
}

export interface ResearchSearchResult {
  intent: ResearchSearchIntent;
  retrieval: ResearchSearchRetrievalState;
  evidence: WorkspaceEvidenceResult[];
}

export interface ResearchTypedSavedSearchResult {
  saved_search_id: string;
  name: string;
  description: string | null;
  intent: ResearchSearchIntent;
  created_at: string;
  updated_at: string;
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
  researchOverview(): Promise<ResearchOverview>;
  filterResearchNotes(tags: string[], collections: string[]): Promise<ResearchNoteFilterResult>;
  createResearchNote(
    evidence: WorkspaceEvidenceResult,
    body: string,
  ): Promise<ResearchNoteResult>;
  updateResearchNote(
    note: ResearchNoteResult,
    update: ResearchNoteUpdate,
  ): Promise<ResearchNoteResult>;
  deleteResearchNote(note: ResearchNoteResult): Promise<void>;
  openResearchNoteEvidence(note: ResearchNoteResult): Promise<ResearchNoteEvidenceResult>;
  executeResearchSearch(intent: ResearchSearchIntent): Promise<ResearchSearchResult>;
  listTypedSavedSearches(): Promise<ResearchTypedSavedSearchResult[]>;
  createTypedSavedSearch(
    name: string,
    description: string | null,
    intent: ResearchSearchIntent,
  ): Promise<ResearchTypedSavedSearchResult>;
  inspectTypedSavedSearch(savedSearchId: string): Promise<ResearchTypedSavedSearchResult>;
  replaceTypedSavedSearch(
    saved: ResearchTypedSavedSearchResult,
    name: string,
    description: string | null,
    intent: ResearchSearchIntent,
  ): Promise<ResearchTypedSavedSearchResult>;
  runTypedSavedSearch(saved: ResearchTypedSavedSearchResult): Promise<ResearchSearchResult>;
  deleteTypedSavedSearch(saved: ResearchTypedSavedSearchResult): Promise<void>;
}

const DESKTOP_PROTOCOL_MESSAGES = {
  invalid: "Scholion desktop bridge returned an invalid response",
  incompatible: "Scholion desktop bridge returned an incompatible response",
  failure: "Scholion could not complete that request",
} as const;

function normalizeLabels(values: string[]): string[] {
  const labels = new Map<string, string>();
  values.forEach((raw) => {
    const value = raw.trim();
    if (value) labels.set(value.toLocaleLowerCase(), value);
  });
  return [...labels.values()].sort((left, right) => left.localeCompare(right));
}

function containsLabel(values: string[], requested: string): boolean {
  const target = requested.toLocaleLowerCase();
  return values.some((value) => value.toLocaleLowerCase() === target);
}

function defaultResearchSearchIntent(queryText: string): ResearchSearchIntent {
  return {
    query_text: queryText,
    phrase: false,
    operator: "any",
    speaker_refs: [],
    languages: [],
    document_ids: [],
    sort: "relevance",
    limit: 20,
    retrieval_mode: "lexical",
    context_segments: 1,
    tags: [],
    collections: [],
    note_text: null,
    with_notes: false,
  };
}

function copyResearchSearchIntent(intent: ResearchSearchIntent): ResearchSearchIntent {
  return {
    ...intent,
    speaker_refs: [...intent.speaker_refs],
    languages: [...intent.languages],
    document_ids: [...intent.document_ids],
    tags: [...intent.tags],
    collections: [...intent.collections],
  };
}

function copyTypedSavedSearch(
  saved: ResearchTypedSavedSearchResult,
): ResearchTypedSavedSearchResult {
  return { ...saved, intent: copyResearchSearchIntent(saved.intent) };
}

class TauriDesktopClient implements DesktopClient {
  private request<T>(method: string, params: Record<string, unknown>): Promise<T> {
    return invokeNativeProtocol<T>(
      "desktop_request",
      method,
      params,
      DESKTOP_PROTOCOL_MESSAGES,
    );
  }

  async chooseFiles(kind: LocationKind): Promise<string[]> {
    const { open } = await import("@tauri-apps/plugin-dialog");
    const filters =
      kind === "transcript-library"
        ? [{ name: "Scholion transcript", extensions: ["json"] }]
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

  researchOverview(): Promise<ResearchOverview> {
    return this.request("workspace.research.overview", {});
  }

  filterResearchNotes(
    tags: string[],
    collections: string[],
  ): Promise<ResearchNoteFilterResult> {
    return this.request("workspace.research.notes.filter", {
      tags,
      collections,
    });
  }

  createResearchNote(
    evidence: WorkspaceEvidenceResult,
    body: string,
  ): Promise<ResearchNoteResult> {
    return this.request("workspace.research.note.create", {
      document_id: evidence.document_id,
      canonical_sha256: evidence.canonical_sha256,
      segment_ids: evidence.segment_ids,
      body,
      start_seconds: evidence.start_seconds,
      end_seconds: evidence.end_seconds,
    });
  }

  updateResearchNote(
    note: ResearchNoteResult,
    update: ResearchNoteUpdate,
  ): Promise<ResearchNoteResult> {
    return this.request("workspace.research.note.update", {
      note_id: note.note_id,
      expected_updated_at: note.updated_at,
      body: update.body,
      tags: update.tags,
      collections: update.collections,
    });
  }

  async deleteResearchNote(note: ResearchNoteResult): Promise<void> {
    await this.request("workspace.research.note.delete", {
      note_id: note.note_id,
      expected_updated_at: note.updated_at,
    });
  }

  openResearchNoteEvidence(note: ResearchNoteResult): Promise<ResearchNoteEvidenceResult> {
    return this.request("workspace.research.note.evidence", {
      note_id: note.note_id,
      context_segments: 1,
    });
  }

  executeResearchSearch(intent: ResearchSearchIntent): Promise<ResearchSearchResult> {
    return this.request("workspace.research.search.execute", { intent });
  }

  listTypedSavedSearches(): Promise<ResearchTypedSavedSearchResult[]> {
    return this.request("workspace.research.search.saved.list", { limit: 200 });
  }

  createTypedSavedSearch(
    name: string,
    description: string | null,
    intent: ResearchSearchIntent,
  ): Promise<ResearchTypedSavedSearchResult> {
    return this.request("workspace.research.search.saved.create", {
      name,
      description,
      intent,
    });
  }

  inspectTypedSavedSearch(savedSearchId: string): Promise<ResearchTypedSavedSearchResult> {
    return this.request("workspace.research.search.saved.inspect", {
      saved_search_id: savedSearchId,
    });
  }

  replaceTypedSavedSearch(
    saved: ResearchTypedSavedSearchResult,
    name: string,
    description: string | null,
    intent: ResearchSearchIntent,
  ): Promise<ResearchTypedSavedSearchResult> {
    return this.request("workspace.research.search.saved.replace", {
      saved_search_id: saved.saved_search_id,
      expected_updated_at: saved.updated_at,
      name,
      description,
      intent,
    });
  }

  runTypedSavedSearch(saved: ResearchTypedSavedSearchResult): Promise<ResearchSearchResult> {
    return this.request("workspace.research.search.saved.run", {
      saved_search_id: saved.saved_search_id,
    });
  }

  async deleteTypedSavedSearch(saved: ResearchTypedSavedSearchResult): Promise<void> {
    await this.request("workspace.research.search.saved.delete", {
      saved_search_id: saved.saved_search_id,
      expected_updated_at: saved.updated_at,
    });
  }
}

class MockDesktopClient implements DesktopClient {
  private locations: LibraryLocation[] = [];
  private researchMutationVersion = 0;
  private researchNotes: ResearchNoteResult[] = [
    {
      note_id: "note-7",
      body: "Follow up on ABC governance during the next interview.",
      document_id: "interview-42",
      canonical_sha256: "a".repeat(64),
      segment_ids: ["segment-17"],
      start_seconds: 862.1,
      end_seconds: 870.4,
      current: true,
      tags: ["program", "governance"],
      collections: ["Oral histories"],
      created_at: "2026-08-19T19:20:00+00:00",
      updated_at: "2026-08-19T19:25:00+00:00",
    },
    {
      note_id: "note-older",
      body: "Earlier interpretation retained for provenance.",
      document_id: "interview-11",
      canonical_sha256: "c".repeat(64),
      segment_ids: ["segment-3"],
      start_seconds: 128.4,
      end_seconds: 135.2,
      current: false,
      tags: ["review"],
      collections: ["Field notes"],
      created_at: "2026-08-18T14:10:00+00:00",
      updated_at: "2026-08-18T14:10:00+00:00",
    },
  ];
  private typedSavedSearches: ResearchTypedSavedSearchResult[] = [
    {
      saved_search_id: "search-9",
      name: "Governance follow-up",
      description: "Questions to revisit across interviews",
      intent: {
        ...defaultResearchSearchIntent("governance"),
        tags: ["governance"],
        with_notes: true,
      },
      created_at: "2026-08-19T19:30:00+00:00",
      updated_at: "2026-08-19T19:31:00+00:00",
    },
  ];

  async chooseFiles(kind: LocationKind): Promise<string[]> {
    return kind === "transcript-library"
      ? ["/Users/susan/Research/interview-01.scholion.json"]
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
    const matchedWord: WorkspaceMatchedWord = {
      segment_id: "segment-17",
      word_index: 2,
      start_seconds: 862.43,
      end_seconds: 862.72,
      text: query,
      speaker_ref: "speaker-1",
      highlighted: true,
    };
    const resultWords: WorkspaceMatchedWord[] = [
      {
        segment_id: "segment-17",
        word_index: 0,
        start_seconds: 862.1,
        end_seconds: 862.35,
        text: "We",
        speaker_ref: "speaker-1",
        highlighted: false,
      },
      {
        segment_id: "segment-17",
        word_index: 1,
        start_seconds: 862.35,
        end_seconds: 862.7,
        text: "started",
        speaker_ref: "speaker-1",
        highlighted: false,
      },
      matchedWord,
      {
        segment_id: "segment-17",
        word_index: 3,
        start_seconds: 862.75,
        end_seconds: 863.1,
        text: "program",
        speaker_ref: "speaker-1",
        highlighted: false,
      },
    ];
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
          matched_words: [matchedWord],
          context_segments: [
            {
              segment_id: "segment-16",
              start_seconds: 851.2,
              end_seconds: 862.0,
              text: "We had already completed two rounds of interviews.",
              speaker_refs: ["speaker-1"],
              words: [],
              is_result_segment: false,
              lexical_match: false,
            },
            {
              segment_id: "segment-17",
              start_seconds: 862.1,
              end_seconds: 870.4,
              text: `We started the ${query} program after the second interview round.`,
              speaker_refs: ["speaker-1"],
              words: resultWords,
              is_result_segment: true,
              lexical_match: true,
            },
            {
              segment_id: "segment-18",
              start_seconds: 870.5,
              end_seconds: 879.8,
              text: "The first cohort joined the following month.",
              speaker_refs: ["speaker-1"],
              words: [],
              is_result_segment: false,
              lexical_match: false,
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

  async researchOverview(): Promise<ResearchOverview> {
    const tagNames = normalizeLabels([
      "program",
      "governance",
      "review",
      ...this.researchNotes.flatMap((note) => note.tags),
    ]);
    const collectionNames = normalizeLabels([
      "Oral histories",
      "Field notes",
      ...this.researchNotes.flatMap((note) => note.collections),
    ]);
    return {
      notes: this.researchNotes.map((note) => ({
        ...note,
        tags: [...note.tags],
        collections: [...note.collections],
      })),
      tags: tagNames.map((name, index) => ({ tag_id: `tag-${index + 1}`, name })),
      collections: collectionNames.map((name, index) => ({
        collection_id: `collection-${index + 1}`,
        name,
      })),
    };
  }

  async filterResearchNotes(
    tags: string[],
    collections: string[],
  ): Promise<ResearchNoteFilterResult> {
    const normalizedTags = normalizeLabels(tags);
    const normalizedCollections = normalizeLabels(collections);
    const notes = this.researchNotes.filter(
      (note) =>
        normalizedTags.every((tag) => containsLabel(note.tags, tag)) &&
        normalizedCollections.every((collection) =>
          containsLabel(note.collections, collection),
        ),
    );
    return {
      tags: normalizedTags,
      collections: normalizedCollections,
      notes: notes.map((note) => ({
        ...note,
        tags: [...note.tags],
        collections: [...note.collections],
      })),
    };
  }

  async createResearchNote(
    evidence: WorkspaceEvidenceResult,
    body: string,
  ): Promise<ResearchNoteResult> {
    const trimmed = body.trim();
    if (!trimmed) throw new Error("Research note cannot be empty");
    const now = this.nextResearchTimestamp();
    const note: ResearchNoteResult = {
      note_id: `note-created-${this.researchNotes.length + 1}`,
      body: trimmed,
      document_id: evidence.document_id,
      canonical_sha256: evidence.canonical_sha256,
      segment_ids: [...evidence.segment_ids],
      start_seconds: evidence.start_seconds,
      end_seconds: evidence.end_seconds,
      current: true,
      tags: [],
      collections: [],
      created_at: now,
      updated_at: now,
    };
    this.researchNotes.unshift(note);
    return { ...note };
  }

  async updateResearchNote(
    note: ResearchNoteResult,
    update: ResearchNoteUpdate,
  ): Promise<ResearchNoteResult> {
    const index = this.researchNotes.findIndex((item) => item.note_id === note.note_id);
    if (index < 0) throw new Error("Research note does not exist");
    const current = this.researchNotes[index];
    if (!current) throw new Error("Research note does not exist");
    if (current.updated_at !== note.updated_at) {
      throw new Error("Research note changed since it was opened; refresh before saving");
    }
    const body = update.body.trim();
    if (!body) throw new Error("Research note cannot be empty");
    const updated: ResearchNoteResult = {
      ...current,
      body,
      tags: normalizeLabels(update.tags),
      collections: normalizeLabels(update.collections),
      updated_at: this.nextResearchTimestamp(),
    };
    this.researchNotes[index] = updated;
    return { ...updated, tags: [...updated.tags], collections: [...updated.collections] };
  }

  async deleteResearchNote(note: ResearchNoteResult): Promise<void> {
    const index = this.researchNotes.findIndex((item) => item.note_id === note.note_id);
    if (index < 0) throw new Error("Research note does not exist");
    const current = this.researchNotes[index];
    if (!current) throw new Error("Research note does not exist");
    if (current.updated_at !== note.updated_at) {
      throw new Error("Research note changed since it was opened; refresh before saving");
    }
    this.researchNotes.splice(index, 1);
  }

  async openResearchNoteEvidence(
    note: ResearchNoteResult,
  ): Promise<ResearchNoteEvidenceResult> {
    const current = this.researchNotes.find((item) => item.note_id === note.note_id);
    if (!current) throw new Error("Research note does not exist");
    const old = !current.current;
    const segmentId = current.segment_ids[0] ?? "segment-unknown";
    const text = old
      ? "Earlier verified evidence retained from this transcript generation."
      : "We started the ABC program after the second interview round.";
    const beforeText = old
      ? "Context from the earlier canonical generation."
      : "We had already completed two rounds of interviews.";
    const afterText = old
      ? "Later context from the same earlier generation."
      : "The first cohort joined the following month.";
    const speakerRef = old ? "speaker-old" : "speaker-1";
    return {
      note_id: current.note_id,
      current: current.current,
      evidence: {
        document_id: current.document_id,
        source_sha256: old ? "d".repeat(64) : "b".repeat(64),
        canonical_sha256: current.canonical_sha256,
        segment_ids: [...current.segment_ids],
        text,
        start_seconds: current.start_seconds,
        end_seconds: current.end_seconds,
        seek_seconds: current.start_seconds,
        languages: [],
        speakers: [
          {
            speaker_ref: speakerRef,
            display_label: old ? "Earlier participant" : "Participant A",
          },
        ],
        matched_words: [],
        context_segments: [
          {
            segment_id: `${segmentId}-before`,
            start_seconds: Math.max(0, current.start_seconds - 8),
            end_seconds: current.start_seconds,
            text: beforeText,
            speaker_refs: [speakerRef],
            words: [],
            is_result_segment: false,
            lexical_match: false,
          },
          {
            segment_id: segmentId,
            start_seconds: current.start_seconds,
            end_seconds: current.end_seconds,
            text,
            speaker_refs: [speakerRef],
            words: [],
            is_result_segment: true,
            lexical_match: false,
          },
          {
            segment_id: `${segmentId}-after`,
            start_seconds: current.end_seconds,
            end_seconds: current.end_seconds + 8,
            text: afterText,
            speaker_refs: [speakerRef],
            words: [],
            is_result_segment: false,
            lexical_match: false,
          },
        ],
        note_count: 1,
        tags: [...current.tags],
        collections: [...current.collections],
      },
    };
  }

  async executeResearchSearch(intent: ResearchSearchIntent): Promise<ResearchSearchResult> {
    const discovery = await this.discoverWorkspace(intent.query_text);
    return {
      intent: copyResearchSearchIntent(intent),
      retrieval: {
        mode: intent.retrieval_mode,
        lexical_backend_id: intent.retrieval_mode === "semantic" ? null : "mock-lexical",
        semantic_backend_id: intent.retrieval_mode === "lexical" ? null : "mock-semantic",
        fusion_profile: intent.retrieval_mode === "hybrid" ? "rrf-k60-v1" : null,
        semantic_profile:
          intent.retrieval_mode === "lexical"
            ? null
            : {
                model_id: "mock-local-embedding",
                resolved_revision: "mock-revision",
                dimensions: 384,
              },
      },
      evidence: discovery.evidence,
    };
  }

  async listTypedSavedSearches(): Promise<ResearchTypedSavedSearchResult[]> {
    return this.typedSavedSearches.map(copyTypedSavedSearch);
  }

  async createTypedSavedSearch(
    name: string,
    description: string | null,
    intent: ResearchSearchIntent,
  ): Promise<ResearchTypedSavedSearchResult> {
    const trimmedName = name.trim();
    if (!trimmedName || !intent.query_text.trim()) {
      throw new Error("Saved search requires a name and query");
    }
    if (
      this.typedSavedSearches.some(
        (saved) => saved.name.toLocaleLowerCase() === trimmedName.toLocaleLowerCase(),
      )
    ) {
      throw new Error("A saved search with that name already exists");
    }
    const now = this.nextResearchTimestamp();
    const normalizedIntent = copyResearchSearchIntent({
      ...intent,
      query_text: intent.query_text.trim(),
    });
    const saved: ResearchTypedSavedSearchResult = {
      saved_search_id: `search-typed-${this.typedSavedSearches.length + 1}`,
      name: trimmedName,
      description: description?.trim() || null,
      intent: normalizedIntent,
      created_at: now,
      updated_at: now,
    };
    this.typedSavedSearches.unshift(saved);
    return copyTypedSavedSearch(saved);
  }

  async inspectTypedSavedSearch(
    savedSearchId: string,
  ): Promise<ResearchTypedSavedSearchResult> {
    const saved = this.typedSavedSearches.find(
      (item) => item.saved_search_id === savedSearchId,
    );
    if (!saved) throw new Error("Saved search does not exist");
    return copyTypedSavedSearch(saved);
  }

  async replaceTypedSavedSearch(
    saved: ResearchTypedSavedSearchResult,
    name: string,
    description: string | null,
    intent: ResearchSearchIntent,
  ): Promise<ResearchTypedSavedSearchResult> {
    const index = this.typedSavedSearches.findIndex(
      (item) => item.saved_search_id === saved.saved_search_id,
    );
    const current = this.typedSavedSearches[index];
    if (index < 0 || !current) throw new Error("Saved search does not exist");
    if (current.updated_at !== saved.updated_at) {
      throw new Error("Saved search changed since it was opened; refresh before saving");
    }
    const trimmedName = name.trim();
    if (!trimmedName || !intent.query_text.trim()) {
      throw new Error("Saved search requires a name and query");
    }
    const now = this.nextResearchTimestamp();
    const updated: ResearchTypedSavedSearchResult = {
      ...current,
      name: trimmedName,
      description: description?.trim() || null,
      intent: copyResearchSearchIntent({
        ...intent,
        query_text: intent.query_text.trim(),
      }),
      updated_at: now,
    };
    this.typedSavedSearches[index] = updated;
    return copyTypedSavedSearch(updated);
  }

  async runTypedSavedSearch(
    saved: ResearchTypedSavedSearchResult,
  ): Promise<ResearchSearchResult> {
    const current = this.typedSavedSearches.find(
      (item) => item.saved_search_id === saved.saved_search_id,
    );
    if (!current) throw new Error("Saved search does not exist");
    return this.executeResearchSearch(current.intent);
  }

  async deleteTypedSavedSearch(saved: ResearchTypedSavedSearchResult): Promise<void> {
    const index = this.typedSavedSearches.findIndex(
      (item) => item.saved_search_id === saved.saved_search_id,
    );
    const current = this.typedSavedSearches[index];
    if (index < 0 || !current) throw new Error("Saved search does not exist");
    if (current.updated_at !== saved.updated_at) {
      throw new Error("Saved search changed since it was opened; refresh before deleting");
    }
    this.typedSavedSearches.splice(index, 1);
  }

  private nextResearchTimestamp(): string {
    this.researchMutationVersion += 1;
    const minute = String(this.researchMutationVersion).padStart(2, "0");
    return `2026-08-19T22:${minute}:00+00:00`;
  }
}

export function createDesktopClient(): DesktopClient {
  const params = new URLSearchParams(window.location.search);
  return params.get("e2e") === "1" ? new MockDesktopClient() : new TauriDesktopClient();
}
