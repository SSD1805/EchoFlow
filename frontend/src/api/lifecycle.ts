export type DeletionScope =
  | "library-view"
  | "derived-artifacts"
  | "execution-state"
  | "canonical-transcript"
  | "research-notes"
  | "saved-searches"
  | "source-recording";

export interface LifecycleDocument {
  document_id: string;
  canonical_sha256: string | null;
  source_name: string | null;
  segment_count: number;
  detected_language: string | null;
  deletion_ready: boolean;
}

export interface DeletionAction {
  target: string;
  description: string;
}

export interface DeletionPlan {
  document_id: string;
  canonical_sha256: string;
  requested_scopes: DeletionScope[];
  effective_scopes: DeletionScope[];
  actions: DeletionAction[];
  preserved_note_count: number;
  affected_saved_search_count: number;
  confirmation_token: string;
}

export interface DeletionReceipt {
  document_id: string;
  executed_targets: string[];
  preserved_note_count: number;
  affected_saved_search_count: number;
}

export interface RetentionPolicy {
  executionDays: number;
  includeIncomplete: boolean;
}

export interface RetentionCandidate {
  job_id: string;
  status: "interrupted" | "failed" | "completed";
  updated_at: string;
  resume_capability_lost: boolean;
}

export interface RetentionPlan {
  policy: {
    execution_days: number;
    include_incomplete: boolean;
  };
  candidates: RetentionCandidate[];
  confirmation_token: string;
}

export interface RetentionReceipt {
  discarded_job_ids: string[];
}

export interface LifecycleClient {
  documents(): Promise<LifecycleDocument[]>;
  planDeletion(
    documentId: string,
    scopes: DeletionScope[],
    allowSource: boolean,
  ): Promise<DeletionPlan>;
  executeDeletion(
    plan: DeletionPlan,
    allowSource: boolean,
  ): Promise<DeletionReceipt>;
  planRetention(policy: RetentionPolicy): Promise<RetentionPlan>;
  executeRetention(plan: RetentionPlan): Promise<RetentionReceipt>;
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

function assertResponse<T>(value: unknown): DesktopResponse<T> {
  if (!value || typeof value !== "object") {
    throw new Error("EchoFlow lifecycle service returned an invalid response");
  }
  const candidate = value as Partial<DesktopResponse<T>>;
  if (
    candidate.protocol_version !== 1 ||
    typeof candidate.request_id !== "string" ||
    typeof candidate.ok !== "boolean"
  ) {
    throw new Error("EchoFlow lifecycle service returned an incompatible response");
  }
  return candidate as DesktopResponse<T>;
}

class TauriLifecycleClient implements LifecycleClient {
  private async request<T>(method: string, params: Record<string, unknown>): Promise<T> {
    const { invoke } = await import("@tauri-apps/api/core");
    const response = assertResponse<T>(
      await invoke<unknown>("lifecycle_request", {
        request: {
          protocol_version: 1,
          request_id: crypto.randomUUID(),
          method,
          params,
        },
      }),
    );
    if (!response.ok || response.result === null) {
      throw new Error(response.error?.message ?? "EchoFlow could not complete that lifecycle request");
    }
    return response.result;
  }

  documents(): Promise<LifecycleDocument[]> {
    return this.request("lifecycle.documents.list", {});
  }

  planDeletion(
    documentId: string,
    scopes: DeletionScope[],
    allowSource: boolean,
  ): Promise<DeletionPlan> {
    return this.request("lifecycle.deletion.plan", {
      document_id: documentId,
      scopes,
      allow_source: allowSource,
    });
  }

  executeDeletion(plan: DeletionPlan, allowSource: boolean): Promise<DeletionReceipt> {
    return this.request("lifecycle.deletion.execute", {
      document_id: plan.document_id,
      scopes: plan.requested_scopes,
      allow_source: allowSource,
      confirmation_token: plan.confirmation_token,
    });
  }

  planRetention(policy: RetentionPolicy): Promise<RetentionPlan> {
    return this.request("lifecycle.retention.plan", {
      execution_days: policy.executionDays,
      include_incomplete: policy.includeIncomplete,
    });
  }

  executeRetention(plan: RetentionPlan): Promise<RetentionReceipt> {
    return this.request("lifecycle.retention.execute", {
      execution_days: plan.policy.execution_days,
      include_incomplete: plan.policy.include_incomplete,
      confirmation_token: plan.confirmation_token,
    });
  }
}

class MockLifecycleClient implements LifecycleClient {
  private documentsState: LifecycleDocument[] = [
    {
      document_id: "interview-42",
      canonical_sha256: "a".repeat(64),
      source_name: "oral-history-42.m4a",
      segment_count: 182,
      detected_language: "en",
      deletion_ready: true,
    },
    {
      document_id: "interview-11",
      canonical_sha256: "c".repeat(64),
      source_name: "field-interview-11.mp4",
      segment_count: 96,
      detected_language: "en",
      deletion_ready: true,
    },
  ];

  async documents(): Promise<LifecycleDocument[]> {
    return this.documentsState.map((item) => ({ ...item }));
  }

  async planDeletion(
    documentId: string,
    scopes: DeletionScope[],
    allowSource: boolean,
  ): Promise<DeletionPlan> {
    const document = this.documentsState.find((item) => item.document_id === documentId);
    if (!document?.canonical_sha256) throw new Error("Transcript is not ready for custody changes");
    if (scopes.length === 0) throw new Error("Choose at least one deletion scope");
    if (scopes.includes("source-recording") && !allowSource) {
      throw new Error("Source recording deletion requires the explicit source safety switch");
    }
    const effective = [...scopes];
    if (scopes.includes("canonical-transcript")) {
      (["library-view", "derived-artifacts", "execution-state"] as DeletionScope[]).forEach((scope) => {
        if (!effective.includes(scope)) effective.push(scope);
      });
    }
    const descriptions: Record<DeletionScope, string> = {
      "library-view": "remove transcript from the rebuildable lexical index",
      "derived-artifacts": "delete regenerable transcript publication exports",
      "execution-state": "delete private checkpoint and intermediate workspace",
      "canonical-transcript": "delete canonical transcript evidence",
      "research-notes": "delete research notes anchored to this exact transcript generation",
      "saved-searches": "delete saved searches explicitly scoped to this transcript",
      "source-recording": "delete the original source recording",
    };
    return {
      document_id: documentId,
      canonical_sha256: document.canonical_sha256,
      requested_scopes: [...scopes],
      effective_scopes: effective,
      actions: effective.map((scope) => ({ target: scope, description: descriptions[scope] })),
      preserved_note_count: scopes.includes("research-notes") ? 0 : 2,
      affected_saved_search_count: 1,
      confirmation_token: `mock-delete:${documentId}:${scopes.join(",")}:${allowSource}`,
    };
  }

  async executeDeletion(plan: DeletionPlan, allowSource: boolean): Promise<DeletionReceipt> {
    const expected = await this.planDeletion(plan.document_id, plan.requested_scopes, allowSource);
    if (expected.confirmation_token !== plan.confirmation_token) {
      throw new Error("Deletion plan changed; preview it again");
    }
    if (plan.effective_scopes.includes("library-view")) {
      this.documentsState = this.documentsState.filter((item) => item.document_id !== plan.document_id);
    }
    return {
      document_id: plan.document_id,
      executed_targets: plan.actions.map((action) => action.target),
      preserved_note_count: plan.preserved_note_count,
      affected_saved_search_count: plan.affected_saved_search_count,
    };
  }

  async planRetention(policy: RetentionPolicy): Promise<RetentionPlan> {
    const candidates: RetentionCandidate[] = [
      {
        job_id: "job-completed-2",
        status: "completed",
        updated_at: "2026-07-01T16:48:00+00:00",
        resume_capability_lost: false,
      },
    ];
    if (policy.includeIncomplete) {
      candidates.push({
        job_id: "job-interrupted-7",
        status: "interrupted",
        updated_at: "2026-07-02T12:35:00+00:00",
        resume_capability_lost: true,
      });
    }
    return {
      policy: {
        execution_days: policy.executionDays,
        include_incomplete: policy.includeIncomplete,
      },
      candidates,
      confirmation_token: `mock-retention:${policy.executionDays}:${policy.includeIncomplete}`,
    };
  }

  async executeRetention(plan: RetentionPlan): Promise<RetentionReceipt> {
    const expected = await this.planRetention({
      executionDays: plan.policy.execution_days,
      includeIncomplete: plan.policy.include_incomplete,
    });
    if (expected.confirmation_token !== plan.confirmation_token) {
      throw new Error("Retention plan changed; preview it again");
    }
    return { discarded_job_ids: plan.candidates.map((candidate) => candidate.job_id) };
  }
}

export function createLifecycleClient(): LifecycleClient {
  const params = new URLSearchParams(window.location.search);
  return params.get("e2e") === "1" ? new MockLifecycleClient() : new TauriLifecycleClient();
}
