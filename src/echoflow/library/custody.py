"""Plan and execute custody-aware deletion and private-state retention."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.library.errors import CustodyOperationError
from echoflow.library.index import IndexedDocument, TranscriptIndex
from echoflow.library.research_state import ResearchNote, ResearchStateStore
from echoflow.library.semantic import SemanticIndex
from echoflow.library.service import (
    LibraryEvidenceReceipt,
    SourceIntegrity,
    TranscriptLibraryService,
)
from echoflow.library.workspace_metadata import WorkspaceMetadataStore
from echoflow.workspace.lifecycle import (
    JobLifecycleRecord,
    JobLifecycleStore,
    JobStatus,
)
from echoflow.workspace.models import WorkspacePaths

_DERIVED_EXPORT_SUFFIXES = (".txt", ".srt", ".vtt")
_MAX_RESEARCH_OBJECTS = 10_000


class DeletionScope(StrEnum):
    """User-selected custody boundary for one transcript deletion plan."""

    LIBRARY_VIEW = "library-view"
    DERIVED_ARTIFACTS = "derived-artifacts"
    EXECUTION_STATE = "execution-state"
    CANONICAL_TRANSCRIPT = "canonical-transcript"
    RESEARCH_NOTES = "research-notes"
    SAVED_SEARCHES = "saved-searches"
    SOURCE_RECORDING = "source-recording"


class DeletionTarget(StrEnum):
    LEXICAL_INDEX = "lexical-index"
    SEMANTIC_INDEX = "semantic-index"
    DERIVED_ARTIFACT = "derived-artifact"
    EXECUTION_STATE = "execution-state"
    RESEARCH_NOTE = "research-note"
    SAVED_SEARCH = "saved-search"
    CANONICAL_TRANSCRIPT = "canonical-transcript"
    SOURCE_RECORDING = "source-recording"


@dataclass(frozen=True, slots=True)
class DeletionAction:
    """One exact mutation in a reviewed deletion plan."""

    target: DeletionTarget
    object_id: str
    description: str
    path: str | None = None

    def __post_init__(self) -> None:
        if not self.object_id.strip():
            raise ValueError("deletion action object_id cannot be empty")
        if not self.description.strip():
            raise ValueError("deletion action description cannot be empty")
        if self.path is not None and not self.path.strip():
            raise ValueError("deletion action path cannot be blank")


@dataclass(frozen=True, slots=True)
class DeletionPlan:
    """A reviewable, plan-bound description of every deletion side effect."""

    document_id: str
    canonical_sha256: str
    requested_scopes: tuple[DeletionScope, ...]
    effective_scopes: tuple[DeletionScope, ...]
    actions: tuple[DeletionAction, ...]
    preserved_note_ids: tuple[str, ...]
    affected_saved_search_ids: tuple[str, ...]
    confirmation_token: str

    def __post_init__(self) -> None:
        if not self.document_id.strip():
            raise ValueError("deletion plan document_id cannot be empty")
        if len(self.canonical_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.canonical_sha256
        ):
            raise ValueError(
                "deletion plan canonical_sha256 must be a lowercase digest"
            )
        if not self.requested_scopes or not self.effective_scopes:
            raise ValueError("deletion plan must contain at least one scope")
        if len(self.requested_scopes) != len(set(self.requested_scopes)):
            raise ValueError("requested deletion scopes must be unique")
        if len(self.effective_scopes) != len(set(self.effective_scopes)):
            raise ValueError("effective deletion scopes must be unique")
        if not self.confirmation_token.strip():
            raise ValueError("deletion confirmation token cannot be empty")


@dataclass(frozen=True, slots=True)
class DeletionReceipt:
    """Completed mutations after a plan-bound confirmation succeeded."""

    document_id: str
    confirmation_token: str
    executed_targets: tuple[DeletionTarget, ...]
    preserved_note_ids: tuple[str, ...]
    affected_saved_search_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    """Automatic-retention policy restricted to private execution workspaces."""

    execution_days: int = 30
    include_incomplete: bool = False

    def __post_init__(self) -> None:
        if self.execution_days < 0 or self.execution_days > 36_500:
            raise ValueError("execution retention days must be between 0 and 36500")


@dataclass(frozen=True, slots=True)
class RetentionCandidate:
    job_id: str
    status: JobStatus
    updated_at: str
    workspace_path: str
    resume_capability_lost: bool

    def __post_init__(self) -> None:
        if not self.job_id.strip() or not self.workspace_path.strip():
            raise ValueError("retention candidate identity and path cannot be empty")


@dataclass(frozen=True, slots=True)
class RetentionPlan:
    """A plan that can delete only private job workspaces, never public evidence."""

    policy: RetentionPolicy
    candidates: tuple[RetentionCandidate, ...]
    confirmation_token: str

    def __post_init__(self) -> None:
        if not self.confirmation_token.strip():
            raise ValueError("retention confirmation token cannot be empty")


@dataclass(frozen=True, slots=True)
class RetentionReceipt:
    confirmation_token: str
    discarded_job_ids: tuple[str, ...]


class LibraryCustodyService:
    """Coordinate deletion without collapsing distinct evidence custody classes."""

    def __init__(
        self,
        transcript_library: TranscriptLibraryService,
        lexical_index: TranscriptIndex,
        semantic_index: SemanticIndex | None,
        lifecycle_store: JobLifecycleStore,
        research_state: ResearchStateStore,
        workspace_metadata: WorkspaceMetadataStore,
        paths: WorkspacePaths,
        file_manager: FileManagerFacade,
    ) -> None:
        self.transcript_library = transcript_library
        self.lexical_index = lexical_index
        self.semantic_index = semantic_index
        self.lifecycle_store = lifecycle_store
        self.research_state = research_state
        self.workspace_metadata = workspace_metadata
        self.paths = paths
        self.file_manager = file_manager

    def plan_deletion(
        self,
        document_id: str,
        scopes: tuple[DeletionScope, ...],
        *,
        allow_source: bool = False,
    ) -> DeletionPlan:
        requested = self._normalized_scopes(scopes)
        effective = self._effective_scopes(requested)
        receipt = self.transcript_library.inspect(document_id)
        document = receipt.document
        canonical_sha256 = self._canonical_digest(document)
        self._validate_source_request(receipt, effective, allow_source=allow_source)

        notes = self._generation_notes(document_id, canonical_sha256)
        saved_search_ids = self._affected_saved_search_ids(document_id)
        preserved_note_ids = (
            ()
            if DeletionScope.RESEARCH_NOTES in effective
            else tuple(note.note_id for note in notes)
        )
        actions = self._deletion_actions(
            document,
            canonical_sha256=canonical_sha256,
            scopes=effective,
            note_ids=tuple(note.note_id for note in notes),
            saved_search_ids=saved_search_ids,
        )
        token = self._deletion_token(
            document_id,
            canonical_sha256,
            requested,
            effective,
            actions,
            preserved_note_ids,
            saved_search_ids,
        )
        return DeletionPlan(
            document_id=document_id,
            canonical_sha256=canonical_sha256,
            requested_scopes=requested,
            effective_scopes=effective,
            actions=actions,
            preserved_note_ids=preserved_note_ids,
            affected_saved_search_ids=saved_search_ids,
            confirmation_token=token,
        )

    def execute_deletion(
        self,
        document_id: str,
        scopes: tuple[DeletionScope, ...],
        *,
        confirmation_token: str,
        allow_source: bool = False,
    ) -> DeletionReceipt:
        plan = self.plan_deletion(document_id, scopes, allow_source=allow_source)
        if confirmation_token != plan.confirmation_token:
            raise CustodyOperationError(
                "Deletion plan changed or confirmation token is invalid; "
                "review the plan again"
            )
        self._validate_destructive_inputs(plan)
        executed: list[DeletionTarget] = []
        for action in plan.actions:
            self._execute_action(action)
            executed.append(action.target)
        return DeletionReceipt(
            document_id=plan.document_id,
            confirmation_token=plan.confirmation_token,
            executed_targets=tuple(executed),
            preserved_note_ids=plan.preserved_note_ids,
            affected_saved_search_ids=plan.affected_saved_search_ids,
        )

    def plan_retention(
        self,
        policy: RetentionPolicy,
        *,
        now: datetime | None = None,
    ) -> RetentionPlan:
        current = self._aware_now(now)
        cutoff = current - timedelta(days=policy.execution_days)
        candidates = tuple(
            candidate
            for record in self.lifecycle_store.list_records()
            if (
                candidate := self._retention_candidate(
                    record,
                    cutoff=cutoff,
                    include_incomplete=policy.include_incomplete,
                )
            )
            is not None
        )
        ordered = tuple(
            sorted(candidates, key=lambda item: (item.updated_at, item.job_id))
        )
        return RetentionPlan(
            policy=policy,
            candidates=ordered,
            confirmation_token=self._retention_token(policy, ordered),
        )

    def execute_retention(
        self,
        policy: RetentionPolicy,
        *,
        confirmation_token: str,
        now: datetime | None = None,
    ) -> RetentionReceipt:
        plan = self.plan_retention(policy, now=now)
        if confirmation_token != plan.confirmation_token:
            raise CustodyOperationError(
                "Retention plan changed or confirmation token is invalid; "
                "review the plan again"
            )
        discarded: list[str] = []
        for candidate in plan.candidates:
            workspace = Path(candidate.workspace_path)
            self._validate_workspace_path(workspace)
            if workspace.is_dir():
                self.file_manager.delete_directory(workspace)
                discarded.append(candidate.job_id)
        return RetentionReceipt(
            confirmation_token=plan.confirmation_token,
            discarded_job_ids=tuple(discarded),
        )

    @staticmethod
    def _normalized_scopes(
        scopes: tuple[DeletionScope, ...],
    ) -> tuple[DeletionScope, ...]:
        if not scopes:
            raise ValueError("at least one deletion scope is required")
        selected = set(scopes)
        return tuple(scope for scope in DeletionScope if scope in selected)

    @staticmethod
    def _effective_scopes(
        requested: tuple[DeletionScope, ...],
    ) -> tuple[DeletionScope, ...]:
        expanded = set(requested)
        if DeletionScope.CANONICAL_TRANSCRIPT in expanded:
            expanded.update(
                {
                    DeletionScope.LIBRARY_VIEW,
                    DeletionScope.DERIVED_ARTIFACTS,
                    DeletionScope.EXECUTION_STATE,
                }
            )
        return tuple(scope for scope in DeletionScope if scope in expanded)

    @staticmethod
    def _canonical_digest(document: IndexedDocument) -> str:
        if document.canonical_sha256 is None:
            raise CustodyOperationError(
                "Transcript index predates canonical hashing; rebuild the library "
                "before deletion"
            )
        return document.canonical_sha256

    @staticmethod
    def _validate_source_request(
        receipt: LibraryEvidenceReceipt,
        scopes: tuple[DeletionScope, ...],
        *,
        allow_source: bool,
    ) -> None:
        if DeletionScope.SOURCE_RECORDING not in scopes:
            return
        if not allow_source:
            raise CustodyOperationError(
                "Source recording deletion requires the explicit allow-source "
                "safety switch"
            )
        if receipt.document.source_path is None:
            raise CustodyOperationError("Source recording path is unavailable")
        if receipt.source_integrity is not SourceIntegrity.MATCHES:
            raise CustodyOperationError(
                "Source recording no longer matches the bytes used for transcription; "
                "refusing deletion"
            )

    def _generation_notes(
        self, document_id: str, canonical_sha256: str
    ) -> tuple[ResearchNote, ...]:
        return tuple(
            note
            for note in self.research_state.notes(
                document_id=document_id,
                limit=_MAX_RESEARCH_OBJECTS,
            )
            if note.anchor.canonical_sha256 == canonical_sha256
        )

    def _affected_saved_search_ids(self, document_id: str) -> tuple[str, ...]:
        return tuple(
            saved.saved_search_id
            for saved in self.workspace_metadata.saved_searches(
                limit=_MAX_RESEARCH_OBJECTS
            )
            if document_id in saved.intent.query.document_ids
        )

    def _deletion_actions(
        self,
        document: IndexedDocument,
        *,
        canonical_sha256: str,
        scopes: tuple[DeletionScope, ...],
        note_ids: tuple[str, ...],
        saved_search_ids: tuple[str, ...],
    ) -> tuple[DeletionAction, ...]:
        actions: list[DeletionAction] = []
        if DeletionScope.LIBRARY_VIEW in scopes:
            actions.extend(self._library_actions(document.document_id))
        if DeletionScope.DERIVED_ARTIFACTS in scopes:
            actions.extend(self._derived_artifact_actions(document))
        if DeletionScope.EXECUTION_STATE in scopes:
            action = self._execution_action(document.document_id)
            if action is not None:
                actions.append(action)
        if DeletionScope.CANONICAL_TRANSCRIPT in scopes:
            actions.append(
                DeletionAction(
                    target=DeletionTarget.CANONICAL_TRANSCRIPT,
                    object_id=canonical_sha256,
                    path=document.canonical_path,
                    description="delete canonical transcript evidence",
                )
            )
        if DeletionScope.SOURCE_RECORDING in scopes:
            source_path = document.source_path
            if source_path is None:
                raise CustodyOperationError("Source recording path is unavailable")
            actions.append(
                DeletionAction(
                    target=DeletionTarget.SOURCE_RECORDING,
                    object_id=document.source_sha256,
                    path=source_path,
                    description="delete the original source recording",
                )
            )
        if DeletionScope.SAVED_SEARCHES in scopes:
            actions.extend(self._saved_search_actions(saved_search_ids))
        if DeletionScope.RESEARCH_NOTES in scopes:
            actions.extend(self._research_actions(note_ids))
        return tuple(actions)

    def _library_actions(self, document_id: str) -> tuple[DeletionAction, ...]:
        actions = [
            DeletionAction(
                target=DeletionTarget.LEXICAL_INDEX,
                object_id=document_id,
                description="remove transcript from the rebuildable lexical index",
            )
        ]
        if self.semantic_index is not None and self.semantic_index.state() is not None:
            actions.append(
                DeletionAction(
                    target=DeletionTarget.SEMANTIC_INDEX,
                    object_id="semantic-corpus",
                    description=(
                        "clear the rebuildable semantic corpus because its fingerprint "
                        "would otherwise reference removed evidence"
                    ),
                )
            )
        return tuple(actions)

    def _derived_artifact_actions(
        self, document: IndexedDocument
    ) -> tuple[DeletionAction, ...]:
        canonical = Path(document.canonical_path)
        actions: list[DeletionAction] = []
        for suffix in _DERIVED_EXPORT_SUFFIXES:
            candidate = canonical.with_suffix(suffix)
            if self.file_manager.file_exists(candidate):
                actions.append(
                    DeletionAction(
                        target=DeletionTarget.DERIVED_ARTIFACT,
                        object_id=suffix.removeprefix("."),
                        path=str(candidate),
                        description=f"delete regenerable {suffix} publication export",
                    )
                )
        return tuple(actions)

    def _execution_action(self, document_id: str) -> DeletionAction | None:
        record = next(
            (
                item
                for item in self.lifecycle_store.list_records()
                if item.job_id.value == document_id
            ),
            None,
        )
        if record is None:
            return None
        workspace = self.paths.jobs_dir / document_id
        if not workspace.is_dir():
            return None
        self._validate_workspace_path(workspace)
        return DeletionAction(
            target=DeletionTarget.EXECUTION_STATE,
            object_id=document_id,
            path=str(workspace),
            description=(
                "delete private checkpoints/intermediates while preserving lifecycle "
                "metadata and public evidence"
            ),
        )

    @staticmethod
    def _research_actions(note_ids: tuple[str, ...]) -> tuple[DeletionAction, ...]:
        return tuple(
            DeletionAction(
                target=DeletionTarget.RESEARCH_NOTE,
                object_id=note_id,
                description="delete authoritative user-authored note",
            )
            for note_id in note_ids
        )

    @staticmethod
    def _saved_search_actions(
        saved_search_ids: tuple[str, ...],
    ) -> tuple[DeletionAction, ...]:
        return tuple(
            DeletionAction(
                target=DeletionTarget.SAVED_SEARCH,
                object_id=saved_search_id,
                description="delete authoritative document-scoped saved search",
            )
            for saved_search_id in saved_search_ids
        )

    def _validate_destructive_inputs(self, plan: DeletionPlan) -> None:
        for action in plan.actions:
            if action.target is DeletionTarget.CANONICAL_TRANSCRIPT:
                self._validate_canonical_path(action, plan.canonical_sha256)
            elif (
                action.target is DeletionTarget.EXECUTION_STATE
                and action.path is not None
            ):
                self._validate_workspace_path(Path(action.path))

    def _validate_canonical_path(
        self, action: DeletionAction, canonical_sha256: str
    ) -> None:
        if action.path is None:
            raise CustodyOperationError("Canonical deletion path is unavailable")
        path = Path(action.path)
        if not self.file_manager.file_exists(path):
            raise CustodyOperationError(
                "Canonical transcript disappeared before deletion"
            )
        digest = hashlib.sha256(self.file_manager.read_file(path)).hexdigest()
        if digest != canonical_sha256:
            raise CustodyOperationError(
                "Canonical transcript changed after indexing; rebuild and review "
                "deletion again"
            )

    def _execute_action(self, action: DeletionAction) -> None:
        if action.target is DeletionTarget.LEXICAL_INDEX:
            self.lexical_index.remove(action.object_id)
            return
        if action.target is DeletionTarget.SEMANTIC_INDEX:
            if self.semantic_index is not None:
                self.semantic_index.clear()
            return
        if action.target is DeletionTarget.RESEARCH_NOTE:
            self.research_state.delete_note(action.object_id)
            return
        if action.target is DeletionTarget.SAVED_SEARCH:
            self.workspace_metadata.delete_saved_search(action.object_id)
            return
        if action.target is DeletionTarget.EXECUTION_STATE:
            if action.path is not None and Path(action.path).is_dir():
                self.file_manager.delete_directory(action.path)
            return
        if action.path is not None and self.file_manager.file_exists(action.path):
            self.file_manager.delete_file(action.path)

    def _retention_candidate(
        self,
        record: JobLifecycleRecord,
        *,
        cutoff: datetime,
        include_incomplete: bool,
    ) -> RetentionCandidate | None:
        if record.status is JobStatus.RUNNING:
            return None
        if record.status is not JobStatus.COMPLETED and not include_incomplete:
            return None
        updated = self._parse_timestamp(record.updated_at)
        if updated > cutoff:
            return None
        workspace = self.paths.jobs_dir / record.job_id.value
        if not workspace.is_dir():
            return None
        self._validate_workspace_path(workspace)
        return RetentionCandidate(
            job_id=record.job_id.value,
            status=record.status,
            updated_at=record.updated_at,
            workspace_path=str(workspace),
            resume_capability_lost=record.status is not JobStatus.COMPLETED,
        )

    def _validate_workspace_path(self, workspace: Path) -> None:
        jobs_dir = self.paths.jobs_dir.resolve(strict=False)
        resolved = workspace.expanduser().resolve(strict=False)
        if resolved.parent != jobs_dir:
            raise CustodyOperationError(
                "Refusing to delete a workspace outside EchoFlow's private "
                "jobs directory"
            )

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise CustodyOperationError(
                "Job lifecycle timestamp is invalid; refusing retention cleanup",
                cause=exc,
            ) from exc
        if parsed.tzinfo is None:
            raise CustodyOperationError(
                "Job lifecycle timestamp lacks timezone; refusing retention cleanup"
            )
        return parsed.astimezone(UTC)

    @staticmethod
    def _aware_now(value: datetime | None) -> datetime:
        current = datetime.now(UTC) if value is None else value
        if current.tzinfo is None:
            raise ValueError("retention clock must be timezone-aware")
        return current.astimezone(UTC)

    @staticmethod
    def _deletion_token(
        document_id: str,
        canonical_sha256: str,
        requested: tuple[DeletionScope, ...],
        effective: tuple[DeletionScope, ...],
        actions: tuple[DeletionAction, ...],
        preserved_note_ids: tuple[str, ...],
        affected_saved_search_ids: tuple[str, ...],
    ) -> str:
        parts = [
            "delete-v1",
            document_id,
            canonical_sha256,
            *(f"requested:{scope.value}" for scope in requested),
            *(f"effective:{scope.value}" for scope in effective),
            *(f"preserved-note:{note_id}" for note_id in preserved_note_ids),
            *(
                f"affected-saved-search:{saved_search_id}"
                for saved_search_id in affected_saved_search_ids
            ),
            *(
                f"action:{item.target.value}:{item.object_id}:{item.path or ''}"
                for item in actions
            ),
        ]
        digest = hashlib.sha256("\n".join(parts).encode()).hexdigest()
        return f"delete:{document_id}:{canonical_sha256[:12]}:{digest[:16]}"

    @staticmethod
    def _retention_token(
        policy: RetentionPolicy,
        candidates: tuple[RetentionCandidate, ...],
    ) -> str:
        parts = [
            "retention-v1",
            str(policy.execution_days),
            str(policy.include_incomplete),
            *(
                f"{item.job_id}:{item.status.value}:{item.updated_at}:"
                f"{item.workspace_path}"
                for item in candidates
            ),
        ]
        digest = hashlib.sha256("\n".join(parts).encode()).hexdigest()
        return f"retention:{digest[:24]}"
