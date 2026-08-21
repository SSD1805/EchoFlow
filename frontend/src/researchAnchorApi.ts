import type { ResearchNoteResult } from "./api/desktop";
import { invokeNativeProtocol } from "./api/nativeProtocol";

export type ResearchAnchorStatus = "current_verified" | "older_verified" | "unavailable";

export interface ResearchAnchorEvidencePreview {
  document_id: string;
  canonical_sha256: string;
  segment_ids: string[];
  start_seconds: number;
  end_seconds: number;
  seek_seconds: number;
  text: string;
}

export interface ResearchAnchorHistoryEntry {
  revision: number;
  canonical_sha256: string;
  segment_ids: string[];
  start_seconds: number;
  end_seconds: number;
  replaced_at: string;
}

export interface ResearchAnchorReviewResult {
  note_id: string;
  updated_at: string;
  status: ResearchAnchorStatus;
  anchored: ResearchAnchorEvidencePreview | null;
  candidate: ResearchAnchorEvidencePreview | null;
  history: ResearchAnchorHistoryEntry[];
}

interface ReanchorResult {
  note_id: string;
  updated_at: string;
  canonical_sha256: string;
  current: boolean;
}

const ANCHOR_PROTOCOL_MESSAGES = {
  invalid: "EchoFlow desktop bridge returned an incompatible response",
  incompatible: "EchoFlow desktop bridge returned an incompatible response",
  failure: "EchoFlow could not complete that request",
} as const;

let mockReanchored = false;

function isMockMode(): boolean {
  return new URLSearchParams(window.location.search).get("e2e") === "1";
}

function request<T>(method: string, params: Record<string, unknown>): Promise<T> {
  return invokeNativeProtocol<T>(
    "desktop_request",
    method,
    params,
    ANCHOR_PROTOCOL_MESSAGES,
  );
}

function mockPreview(
  note: ResearchNoteResult,
  canonicalSha256: string,
  text: string,
): ResearchAnchorEvidencePreview {
  return {
    document_id: note.document_id,
    canonical_sha256: canonicalSha256,
    segment_ids: [...note.segment_ids],
    start_seconds: note.start_seconds,
    end_seconds: note.end_seconds,
    seek_seconds: note.start_seconds,
    text,
  };
}

export async function reviewResearchAnchor(
  note: ResearchNoteResult,
): Promise<ResearchAnchorReviewResult> {
  if (isMockMode()) {
    if (mockReanchored) {
      return {
        note_id: note.note_id,
        updated_at: "2026-08-20T08:10:00+00:00",
        status: "current_verified",
        anchored: mockPreview(note, "d".repeat(64), "Current reviewed evidence."),
        candidate: null,
        history: [
          {
            revision: 1,
            canonical_sha256: note.canonical_sha256,
            segment_ids: [...note.segment_ids],
            start_seconds: note.start_seconds,
            end_seconds: note.end_seconds,
            replaced_at: "2026-08-20T08:10:00+00:00",
          },
        ],
      };
    }
    return {
      note_id: note.note_id,
      updated_at: note.updated_at,
      status: "older_verified",
      anchored: mockPreview(note, note.canonical_sha256, "Earlier verified evidence."),
      candidate: mockPreview(note, "d".repeat(64), "Current reviewed evidence."),
      history: [],
    };
  }
  return request<ResearchAnchorReviewResult>("workspace.research.note.anchor.review", {
    note_id: note.note_id,
    context_segments: 1,
  });
}

export async function reanchorResearchNote(
  review: ResearchAnchorReviewResult,
): Promise<ReanchorResult> {
  if (!review.candidate) {
    throw new Error("No reviewed current evidence candidate is available.");
  }
  if (isMockMode()) {
    mockReanchored = true;
    return {
      note_id: review.note_id,
      updated_at: "2026-08-20T08:10:00+00:00",
      canonical_sha256: review.candidate.canonical_sha256,
      current: true,
    };
  }
  return request<ReanchorResult>("workspace.research.note.anchor.reanchor", {
    note_id: review.note_id,
    expected_updated_at: review.updated_at,
    expected_candidate_sha256: review.candidate.canonical_sha256,
  });
}
