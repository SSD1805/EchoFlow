import { invokeNativeProtocol } from "./nativeProtocol";

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

const LIFECYCLE_PROTOCOL_MESSAGES = {
  invalid: "Scholion storage service returned an invalid response",
  incompatible: "Scholion storage service returned an incompatible response",
  failure: "Scholion could not complete that storage request",
} as const;

const DELETION_ACTION_COPY: Readonly<Record<string, string>> = {
  "library-view": "Remove this transcript from Library search",
  "lexical-index": "Remove this transcript from Library search",
  "semantic-index": "Update Library semantic search after removing this transcript",
  "derived-artifacts": "Delete exported transcript copies",
  "derived-artifact": "Delete an exported transcript copy",
  "execution-state": "Delete temporary processing files and saved progress",
  "canonical-transcript": "Delete the Scholion transcript",
  "research-notes": "Delete notes attached to this transcript version",
  "research-note": "Delete a note attached to this transcript version",
  "saved-searches": "Delete saved searches limited to this transcript",
  "saved-search": "Delete a saved search limited to this transcript",
  "source-recording": "Delete the original recording",
};

function presentDeletionPlan(plan: DeletionPlan): DeletionPlan {
  return {
    ...plan,
    actions: plan.actions.map((action) => ({
      ...action,
      description: DELETION_ACTION_COPY[action.target] ?? action.description,
    })),
  };
}

class TauriLifecycleClient implements LifecycleClient {
  private request<T>(method: string, params: Record<string, unknown>): Promise<T> {
    return invokeNativeProtocol<T>(
      "lifecycle_request",
      method,
      params,
      LIFECYCLE_PROTOCOL_MESSAGES,
    );
  }

  documents(): Promise<LifecycleDocument[]> {
    return this.request("lifecycle.documents.list", {});
  }

  async planDeletion(
    documentId: string,
    scopes: DeletionScope[],
    allowSource: boolean,
  ): Promise<DeletionPlan> {
    const plan = await this.request<DeletionPlan>("lifecycle.deletion.plan", {
      document_id: documentId,
      scopes,
      allow_source: allowSource,
    });
    return presentDeletionPlan(plan);
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
    if (!document?.canonical_sha256) throw new Error("Transcript is not ready for deletion review");
    if (scopes.length === 0) throw new Error("Choose at least one item to remove");
    if (scopes.includes("source-recording") && !allowSource) {
      throw new Error("Confirm original recording deletion before continuing");
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
    return presentDeletionPlan({
      document_id: documentId,
      canonical_sha256: document.canonical_sha256,
      requested_scopes: [...scopes],
      effective_scopes: effective,
      actions: effective.map((scope) => ({ target: scope, description: descriptions[scope] })),
      preserved_note_count: scopes.includes("research-notes") ? 0 : 2,
      affected_saved_search_count: 1,
      confirmation_token: `mock-delete:${documentId}:${scopes.join(",")}:${allowSource}`,
    });
  }

  async executeDeletion(plan: DeletionPlan, allowSource: boolean): Promise<DeletionReceipt> {
    const expected = await this.planDeletion(plan.document_id, plan.requested_scopes, allowSource);
    if (expected.confirmation_token !== plan.confirmation_token) {
      throw new Error("Deletion choices changed; review them again");
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
      throw new Error("Cleanup choices changed; preview them again");
    }
    return { discarded_job_ids: plan.candidates.map((candidate) => candidate.job_id) };
  }
}

export function createLifecycleClient(): LifecycleClient {
  const params = new URLSearchParams(window.location.search);
  return params.get("e2e") === "1" ? new MockLifecycleClient() : new TauriLifecycleClient();
}
