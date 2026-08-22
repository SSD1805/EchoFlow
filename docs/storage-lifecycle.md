# Storage and lifecycle controls

Scholion treats local storage changes as custody decisions, not generic file-manager actions.

The desktop **Storage** workspace is the ordinary user surface for the existing safe-deletion and private-retention contracts. It does not own deletion policy. Python calculates a plan, React presents the consequences, and the user must explicitly apply that exact reviewed plan before anything changes.

## Desktop flow

For transcript custody:

1. Choose an indexed transcript.
2. Select one or more explicit custody scopes.
3. Ask Scholion to **Preview deletion plan**.
4. Review the backend-calculated effective scopes and actions.
5. Apply the reviewed plan.

The confirmation token returned with the preview is bound to the exact generation, requested scopes, expanded scopes, affected objects, and preservation state. Execution recalculates the plan. If anything material changed, the old token no longer matches and Scholion refuses the stale request.

The token is a change-detection and confirmation primitive, not an authentication secret.

## Separate custody scopes

The desktop presents the same typed scopes as the application service:

| Scope | Meaning |
|---|---|
| `library-view` | remove rebuildable search/index state |
| `derived-artifacts` | remove regenerable TXT/SRT/WebVTT publications |
| `execution-state` | remove private checkpoints/intermediates for the job |
| `canonical-transcript` | remove canonical transcript JSON and its disposable descendants |
| `research-notes` | remove human-authored notes anchored to the exact current generation |
| `saved-searches` | remove saved searches explicitly constrained to the transcript |
| `source-recording` | remove the original recording after an additional safety gate and provenance check |

Selecting `canonical-transcript` automatically expands only to disposable descendants: library view, derived publications, and private execution state. It does **not** imply deletion of research notes, saved searches, or source media.

## Source recording safety

Source recording removal requires both:

- the explicit `source-recording` scope; and
- a second desktop acknowledgment that enables the backend source safety switch.

Python then verifies that the current recording still matches the source SHA-256 recorded when the transcript was created. If the bytes changed, Scholion refuses the operation rather than using old provenance as permission to modify a different file now occupying the same path.

The desktop never receives the source or canonical filesystem path. The lifecycle DTO exposes only a safe source basename for human identification, generation identity, counts, and backend-generated descriptions.

Filesystem deletion is not a claim of forensic secure erasure. SSD wear levelling, snapshots, backups, sync history, and storage-controller behaviour remain outside Scholion's proof boundary.

## Private processing cleanup

The second Storage surface cleans old private processing workspaces according to a reviewed retention policy.

The default policy is:

```text
execution_days = 30
include_incomplete = false
```

Only completed job workspaces older than the cutoff are included by default. Failed and interrupted workspaces may still contain resumable state, so they are eligible only when `include_incomplete` is explicitly enabled. The preview marks every candidate whose resume capability would be lost. Running jobs are never eligible.

Retention never age-removes:

- canonical transcript JSON;
- source recordings;
- TXT/SRT/WebVTT publications;
- notes, tags, or collections;
- saved searches;
- speaker display names; or
- lightweight lifecycle manifests.

## Native boundary

Lifecycle operations use a dedicated fixed bridge rather than the general desktop bridge:

```text
React Storage workspace
        |
        | lifecycle_request
        v
Tauri fixed command
        |
        | python -m scholion.desktop.custody_bridge
        v
LibraryCustodyService
```

The closed protocol allows only:

```text
lifecycle.documents.list
lifecycle.deletion.plan
lifecycle.deletion.execute
lifecycle.retention.plan
lifecycle.retention.execute
```

React cannot choose a Python module, filesystem path, SQL statement, or arbitrary operation. The Python adapter strips `DeletionAction.path` and `RetentionCandidate.workspace_path` before serialization.

## Failure semantics

The underlying custody executor cannot make SQLite, DuckDB, arbitrary public evidence files, private workspaces, and source media participate in one cross-filesystem ACID transaction.

It therefore orders lower-custody and rebuildable mutations before unique human/source state. If a later operation fails, earlier disposable state may already have changed, but unique research is deliberately not sacrificed first.

See [Safe deletion and retention controls](architecture/safe-deletion-retention.md) for the full application contract and failure-ordering rationale.

## Test contract

The desktop tranche adds coverage for:

- closed lifecycle request methods and bounded parameters;
- duplicate/out-of-range request rejection;
- source-path and canonical-path non-disclosure;
- plan serialization without action paths;
- retention serialization without private workspace paths;
- exact confirmation-token forwarding;
- source safety-switch forwarding;
- canonical-scope expansion presentation;
- source second-guard behaviour;
- retention previews with resume-loss warnings;
- plan-first application; and
- axe accessibility with an open destructive plan.

The existing `LibraryCustodyService` tests remain authoritative for scope expansion, plan recalculation, provenance checks, retention eligibility, mutation ordering, and stale-token refusal.
