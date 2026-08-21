"""Application authority for inspectable Research search intent.

The desktop may collect search controls, but it does not decide how those controls map to
transcript retrieval, research projection filters, or durable saved-search state.  This
module keeps that composition in Python and gives adapters one typed object to round-trip.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from echoflow.library.errors import ResearchStateError
from echoflow.library.index import SearchQuery
from echoflow.library.research_workspace import (
    ResearchQueryFilters,
    ResearchWorkspaceService,
    WorkspaceSearchResponse,
)
from echoflow.library.retrieval import RetrievalMode
from echoflow.library.workspace_metadata import SavedSearch, SavedSearchIntent


@dataclass(frozen=True, slots=True)
class ResearchSearchIntent:
    """One complete, user-authored search request before derived scoping is applied."""

    query: SearchQuery
    filters: ResearchQueryFilters = field(default_factory=ResearchQueryFilters)
    mode: RetrievalMode = RetrievalMode.LEXICAL
    context_segments: int = 1

    def __post_init__(self) -> None:
        if self.query.evidence_scope is not None:
            raise ValueError(
                "research search intent cannot contain a derived evidence scope"
            )
        if self.context_segments < 0 or self.context_segments > 10:
            raise ValueError("context_segments must be between 0 and 10")

    def to_saved_intent(self) -> SavedSearchIntent:
        """Persist only user-authored intent, never runtime evidence identities."""
        return SavedSearchIntent(
            query=self.query,
            mode=self.mode,
            context_segments=self.context_segments,
            tags=self.filters.tags,
            collections=self.filters.collections,
            note_text=self.filters.note_text,
            with_notes=self.filters.with_notes,
        )

    @classmethod
    def from_saved_intent(cls, intent: SavedSearchIntent) -> ResearchSearchIntent:
        return cls(
            query=intent.query,
            filters=ResearchQueryFilters(
                tags=intent.tags,
                collections=intent.collections,
                note_text=intent.note_text,
                with_notes=intent.with_notes,
            ),
            mode=intent.mode,
            context_segments=intent.context_segments,
        )


class ResearchSearchControlService:
    """Execute and persist typed search intent without moving semantics into adapters."""

    def __init__(self, workspace: ResearchWorkspaceService) -> None:
        self.workspace = workspace

    def search(self, intent: ResearchSearchIntent) -> WorkspaceSearchResponse:
        return self.workspace.search(
            intent.query,
            filters=intent.filters,
            mode=intent.mode,
            context_segments=intent.context_segments,
        )

    def list_saved_searches(self, *, limit: int = 200) -> tuple[SavedSearch, ...]:
        """List durable typed search intent through the same workspace authority."""
        return self.workspace.saved_searches(limit=limit)

    def create_saved_search(
        self,
        name: str,
        intent: ResearchSearchIntent,
        *,
        description: str | None = None,
        saved_search_id: str | None = None,
    ) -> SavedSearch:
        return self.workspace.save_search(
            name,
            intent.query,
            filters=intent.filters,
            mode=intent.mode,
            context_segments=intent.context_segments,
            description=description,
            saved_search_id=saved_search_id,
        )

    def inspect_saved_search(self, identifier: str) -> SavedSearch:
        """Resolve one durable saved search or fail through the application error contract."""
        saved = self.workspace.saved_search(identifier)
        if saved is None:
            raise ResearchStateError("Saved search does not exist")
        return saved

    def replace_saved_search(
        self,
        identifier: str,
        *,
        name: str,
        description: str | None,
        intent: ResearchSearchIntent,
        expected_updated_at: str,
    ) -> SavedSearch:
        """Atomically replace display metadata and typed intent with optimistic concurrency."""
        current = self.inspect_saved_search(identifier)
        metadata = self.workspace.metadata
        if metadata is None:
            raise ResearchStateError("Workspace metadata storage is not configured")
        updated = metadata.update_saved_search(
            current.saved_search_id,
            name=name,
            description=description,
            intent=intent.to_saved_intent(),
            expected_updated_at=expected_updated_at,
        )
        if self.workspace.logger is not None:
            self.workspace.logger.info(
                "research_saved_search_updated",
                saved_search_id=updated.saved_search_id,
                retrieval_mode=updated.intent.mode.value,
                context_segments=updated.intent.context_segments,
                tag_count=len(updated.intent.tags),
                collection_count=len(updated.intent.collections),
                speaker_filter_count=len(updated.intent.query.speaker_refs),
                language_filter_count=len(updated.intent.query.languages),
                document_filter_count=len(updated.intent.query.document_ids),
                with_notes=updated.intent.with_notes,
            )
        return updated

    def run_saved_search(
        self, identifier: str
    ) -> tuple[SavedSearch, WorkspaceSearchResponse]:
        """Replay durable intent through the workspace's current evidence/search authority."""
        saved = self.inspect_saved_search(identifier)
        return saved, self.workspace.run_saved_search(saved.saved_search_id)

    def delete_saved_search(
        self,
        identifier: str,
        *,
        expected_updated_at: str,
    ) -> None:
        """Delete durable saved intent with optimistic concurrency."""
        self.workspace.delete_saved_search(
            identifier,
            expected_updated_at=expected_updated_at,
        )
