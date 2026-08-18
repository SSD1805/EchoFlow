"""Compose durable research knowledge with verified transcript retrieval."""

from __future__ import annotations

from dataclasses import dataclass, replace

from echoflow.library.errors import ResearchStateError
from echoflow.library.evidence import EvidenceLocator
from echoflow.library.index import IndexedDocument, SearchQuery
from echoflow.library.research import (
    LocatedSearchPassage,
    ResearchNavigationService,
    ResearchSearchResponse,
)
from echoflow.library.research_projection import (
    EvidenceScopeKey,
    ProjectedEvidenceSummary,
    ResearchProjectionFilter,
    ResearchProjectionIndex,
    ResearchProjectionStatus,
)
from echoflow.library.research_projector import (
    ResearchProjectionSyncReport,
    ResearchStateProjector,
)
from echoflow.library.research_state import (
    ResearchCollection,
    ResearchNote,
    ResearchStateStore,
    ResearchTag,
)
from echoflow.library.retrieval import RetrievalMode
from echoflow.library.service import TranscriptLibraryService


@dataclass(frozen=True, slots=True)
class ResearchQueryFilters:
    """User-facing research-state constraints compiled to projection identities."""

    tags: tuple[str, ...] = ()
    collections: tuple[str, ...] = ()
    note_text: str | None = None
    with_notes: bool = False

    def __post_init__(self) -> None:
        for name, values in (("tags", self.tags), ("collections", self.collections)):
            if any(not value.strip() for value in values):
                raise ValueError(f"{name} cannot contain blank values")
            normalized = tuple(value.strip().casefold() for value in values)
            if len(normalized) != len(set(normalized)):
                raise ValueError(f"{name} cannot contain duplicates")
        if self.note_text is not None and not self.note_text.strip():
            raise ValueError("note_text cannot be blank")

    @property
    def active(self) -> bool:
        return bool(
            self.with_notes
            or self.tags
            or self.collections
            or self.note_text is not None
        )


@dataclass(frozen=True, slots=True)
class ResearchEvidenceView:
    """User-authored state currently associated with one retrieved evidence passage."""

    note_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    collections: tuple[str, ...] = ()

    @property
    def note_count(self) -> int:
        return len(self.note_ids)


@dataclass(frozen=True, slots=True)
class WorkspaceSearchPassage:
    located: LocatedSearchPassage
    research: ResearchEvidenceView


@dataclass(frozen=True, slots=True)
class WorkspaceSearchResponse:
    navigation: ResearchSearchResponse
    filters: ResearchQueryFilters
    results: tuple[WorkspaceSearchPassage, ...]

    def __post_init__(self) -> None:
        if len(self.navigation.results) != len(self.results):
            raise ValueError("workspace results must preserve navigation cardinality")
        if tuple(item.located for item in self.results) != self.navigation.results:
            raise ValueError("workspace results must preserve navigation result order")


@dataclass(frozen=True, slots=True)
class ResearchNoteView:
    note: ResearchNote
    current: bool
    tags: tuple[str, ...]
    collections: tuple[str, ...]


class ResearchWorkspaceService:
    """Present one research workspace across evidence, SQLite, and DuckDB projections."""

    def __init__(
        self,
        transcript_library: TranscriptLibraryService,
        evidence_locator: EvidenceLocator,
        navigation: ResearchNavigationService,
        state: ResearchStateStore,
        projection: ResearchProjectionIndex,
        projector: ResearchStateProjector,
    ) -> None:
        self.transcript_library = transcript_library
        self.evidence_locator = evidence_locator
        self.navigation = navigation
        self.state = state
        self.projection = projection
        self.projector = projector

    def search(
        self,
        query: SearchQuery,
        *,
        filters: ResearchQueryFilters | None = None,
        mode: RetrievalMode = RetrievalMode.LEXICAL,
        context_segments: int = 0,
    ) -> WorkspaceSearchResponse:
        resolved_filters = filters or ResearchQueryFilters()
        self.projector.sync()
        scoped_query = query
        if resolved_filters.active:
            resolved = self._resolve_projection_filter(
                resolved_filters,
                document_ids=query.document_ids,
            )
            scope = (
                () if resolved is None else self.projection.matching_evidence(resolved)
            )
            scoped_query = replace(query, evidence_scope=scope)
        navigation = self.navigation.search(
            scoped_query,
            mode=mode,
            context_segments=context_segments,
        )
        summaries = self._summaries(navigation)
        tag_names = {item.tag_id: item.name for item in self.state.tags()}
        collection_names = {
            item.collection_id: item.name for item in self.state.collections()
        }
        results = tuple(
            WorkspaceSearchPassage(
                located=item,
                research=self._research_view(
                    item,
                    summaries=summaries,
                    tag_names=tag_names,
                    collection_names=collection_names,
                ),
            )
            for item in navigation.results
        )
        return WorkspaceSearchResponse(
            navigation=navigation,
            filters=resolved_filters,
            results=results,
        )

    def add_note(
        self,
        document_id: str,
        segment_ids: tuple[str, ...],
        body: str,
        *,
        tags: tuple[str, ...] = (),
        collections: tuple[str, ...] = (),
        start_seconds: float | None = None,
        end_seconds: float | None = None,
    ) -> ResearchNoteView:
        document = self._document(document_id)
        anchor = self.evidence_locator.resolve_anchor(
            document,
            segment_ids,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
        )
        note = self.state.create_note(
            anchor,
            body,
            tags=tags,
            collections=collections,
        )
        return self._note_view(note)

    def update_note(self, note_id: str, body: str) -> ResearchNoteView:
        return self._note_view(self.state.update_note(note_id, body))

    def delete_note(self, note_id: str) -> None:
        self.state.delete_note(note_id)

    def set_note_tags(self, note_id: str, names: tuple[str, ...]) -> ResearchNoteView:
        return self._note_view(self.state.set_note_tags(note_id, names))

    def set_note_collections(
        self, note_id: str, names: tuple[str, ...]
    ) -> ResearchNoteView:
        return self._note_view(self.state.set_note_collections(note_id, names))

    def note(self, note_id: str) -> ResearchNoteView | None:
        note = self.state.note(note_id)
        return None if note is None else self._note_view(note)

    def notes(
        self,
        *,
        document_id: str | None = None,
        filters: ResearchQueryFilters | None = None,
        limit: int = 1_000,
    ) -> tuple[ResearchNoteView, ...]:
        if limit < 1 or limit > 10_000:
            raise ValueError("note list limit must be between 1 and 10000")
        resolved_filters = filters or ResearchQueryFilters()
        if not resolved_filters.active:
            notes = self.state.notes(document_id=document_id, limit=limit)
            return self._note_views(notes)

        self.projector.sync()
        document_ids = () if document_id is None else (document_id,)
        resolved = self._resolve_projection_filter(
            resolved_filters,
            document_ids=document_ids,
        )
        if resolved is None:
            return ()
        note_ids = self.projection.matching_note_ids(resolved)[:limit]
        return self._note_views(self.state.notes_by_ids(note_ids))

    def tags(self) -> tuple[ResearchTag, ...]:
        return self.state.tags()

    def collections(self) -> tuple[ResearchCollection, ...]:
        return self.state.collections()

    def projection_status(self) -> ResearchProjectionStatus:
        return self.projector.status()

    def sync_projection(self) -> ResearchProjectionSyncReport:
        return self.projector.sync()

    def rebuild_projection(self) -> ResearchProjectionSyncReport:
        return self.projector.rebuild()

    def _resolve_projection_filter(
        self,
        filters: ResearchQueryFilters,
        *,
        document_ids: tuple[str, ...] = (),
    ) -> ResearchProjectionFilter | None:
        tag_ids = self.state.resolve_tag_ids(filters.tags)
        if tag_ids is None:
            return None
        collection_ids = self.state.resolve_collection_ids(filters.collections)
        if collection_ids is None:
            return None
        return ResearchProjectionFilter(
            tag_ids=tag_ids,
            collection_ids=collection_ids,
            document_ids=tuple(sorted(set(document_ids))),
            note_text=filters.note_text,
            require_notes=filters.with_notes,
        )

    def _summaries(
        self, navigation: ResearchSearchResponse
    ) -> dict[EvidenceScopeKey, ProjectedEvidenceSummary]:
        keys = tuple(
            dict.fromkeys(
                (
                    item.evidence.document_id,
                    item.evidence.canonical_sha256,
                    segment_id,
                )
                for item in navigation.results
                for segment_id in item.evidence.result_segment_ids
            )
        )
        return self.projection.summaries(keys)

    @staticmethod
    def _research_view(
        item: LocatedSearchPassage,
        *,
        summaries: dict[EvidenceScopeKey, ProjectedEvidenceSummary],
        tag_names: dict[str, str],
        collection_names: dict[str, str],
    ) -> ResearchEvidenceView:
        note_ids: set[str] = set()
        tag_ids: set[str] = set()
        collection_ids: set[str] = set()
        for segment_id in item.evidence.result_segment_ids:
            key = (
                item.evidence.document_id,
                item.evidence.canonical_sha256,
                segment_id,
            )
            summary = summaries.get(key)
            if summary is None:
                continue
            note_ids.update(summary.note_ids)
            tag_ids.update(summary.tag_ids)
            collection_ids.update(summary.collection_ids)
        return ResearchEvidenceView(
            note_ids=tuple(sorted(note_ids)),
            tags=tuple(sorted(tag_names[tag_id] for tag_id in tag_ids)),
            collections=tuple(
                sorted(
                    collection_names[collection_id] for collection_id in collection_ids
                )
            ),
        )

    def _note_view(self, note: ResearchNote) -> ResearchNoteView:
        return self._note_views((note,))[0]

    def _note_views(
        self, notes: tuple[ResearchNote, ...]
    ) -> tuple[ResearchNoteView, ...]:
        if not notes:
            return ()
        current_documents = {
            document.document_id: document
            for document in self.transcript_library.documents()
        }
        tag_names = {item.tag_id: item.name for item in self.state.tags()}
        collection_names = {
            item.collection_id: item.name for item in self.state.collections()
        }
        return tuple(
            self._note_view_with_maps(
                note,
                current_documents=current_documents,
                tag_names=tag_names,
                collection_names=collection_names,
            )
            for note in notes
        )

    @staticmethod
    def _note_view_with_maps(
        note: ResearchNote,
        *,
        current_documents: dict[str, IndexedDocument],
        tag_names: dict[str, str],
        collection_names: dict[str, str],
    ) -> ResearchNoteView:
        document = current_documents.get(note.anchor.document_id)
        current = bool(
            document is not None
            and document.canonical_sha256 == note.anchor.canonical_sha256
            and document.source_sha256 == note.anchor.source_sha256
        )
        return ResearchNoteView(
            note=note,
            current=current,
            tags=tuple(tag_names[tag_id] for tag_id in note.tag_ids),
            collections=tuple(
                collection_names[collection_id] for collection_id in note.collection_ids
            ),
        )

    def _document(self, document_id: str) -> IndexedDocument:
        document = next(
            (
                item
                for item in self.transcript_library.documents()
                if item.document_id == document_id
            ),
            None,
        )
        if document is None:
            raise ResearchStateError("Transcript is not present in the local library")
        return document
