"""Narrow desktop adapter for typed Research search intent.

React supplies form values only. Python validates the complete intent, executes search
semantics, and performs optimistic saved-search lifecycle operations. Runtime evidence
scopes and filesystem paths never cross this adapter as user-editable state.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from echoflow.desktop.research_serialization import serialize_workspace_passage
from echoflow.library.index import SearchOperator, SearchQuery, SearchSort
from echoflow.library.research_search_controls import (
    ResearchSearchControlService,
    ResearchSearchIntent,
)
from echoflow.library.research_workspace import (
    ResearchQueryFilters,
    ResearchWorkspaceService,
    WorkspaceSearchResponse,
)
from echoflow.library.retrieval import RetrievalMode
from echoflow.library.workspace_metadata import SavedSearch


class _SearchIntentParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_text: str = Field(min_length=1, max_length=4_096)
    phrase: bool = False
    operator: SearchOperator = SearchOperator.ANY
    speaker_refs: tuple[str, ...] = Field(default=(), max_length=100)
    languages: tuple[str, ...] = Field(default=(), max_length=100)
    document_ids: tuple[str, ...] = Field(default=(), max_length=100)
    sort: SearchSort = SearchSort.RELEVANCE
    limit: int = Field(default=20, ge=1, le=1_000)
    retrieval_mode: RetrievalMode = RetrievalMode.LEXICAL
    context_segments: int = Field(default=1, ge=0, le=10)
    tags: tuple[str, ...] = Field(default=(), max_length=100)
    collections: tuple[str, ...] = Field(default=(), max_length=100)
    note_text: str | None = Field(default=None, max_length=4_096)
    with_notes: bool = False

    @field_validator("query_text")
    @classmethod
    def strip_query(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query_text cannot be blank")
        return stripped

    @field_validator("speaker_refs", "languages", "document_ids")
    @classmethod
    def normalize_exact_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("search filters cannot contain blank values")
        if len(normalized) != len(set(normalized)):
            raise ValueError("search filters cannot contain duplicate values")
        return normalized

    @field_validator("tags", "collections")
    @classmethod
    def normalize_labels(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized: dict[str, str] = {}
        for raw in values:
            value = raw.strip()
            if not value:
                raise ValueError("research labels cannot be blank")
            if len(value) > 200:
                raise ValueError("research labels cannot exceed 200 characters")
            if any(character in value for character in ("\r", "\n", "\x00")):
                raise ValueError(
                    "research labels contain unsupported control characters"
                )
            normalized.setdefault(value.casefold(), value)
        return tuple(normalized[key] for key in sorted(normalized))

    @field_validator("note_text")
    @classmethod
    def normalize_note_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    def to_intent(self) -> ResearchSearchIntent:
        return ResearchSearchIntent(
            query=SearchQuery(
                self.query_text,
                phrase=self.phrase,
                operator=self.operator,
                speaker_refs=self.speaker_refs,
                languages=self.languages,
                document_ids=self.document_ids,
                sort=self.sort,
                limit=self.limit,
            ),
            filters=ResearchQueryFilters(
                tags=self.tags,
                collections=self.collections,
                note_text=self.note_text,
                with_notes=self.with_notes,
            ),
            mode=self.retrieval_mode,
            context_segments=self.context_segments,
        )


class _ExecuteParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: _SearchIntentParams


class _ListSavedParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=200, ge=1, le=1_000)


class _CreateSavedParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4_000)
    intent: _SearchIntentParams

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name cannot be blank")
        return stripped

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class _SavedIdentifierParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    saved_search_id: str = Field(min_length=1, max_length=200)

    @field_validator("saved_search_id")
    @classmethod
    def strip_identifier(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("saved_search_id cannot be blank")
        return stripped


class _ReplaceSavedParams(_CreateSavedParams):
    saved_search_id: str = Field(min_length=1, max_length=200)
    expected_updated_at: str = Field(min_length=1, max_length=200)

    @field_validator("saved_search_id", "expected_updated_at")
    @classmethod
    def strip_version_fields(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("saved search identity and version cannot be blank")
        return stripped


class _DeleteSavedParams(_SavedIdentifierParams):
    expected_updated_at: str = Field(min_length=1, max_length=200)

    @field_validator("expected_updated_at")
    @classmethod
    def strip_expected_updated_at(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("expected_updated_at cannot be blank")
        return stripped


def _serialize_intent(intent: ResearchSearchIntent) -> dict[str, object]:
    query = intent.query
    return {
        "query_text": query.text,
        "phrase": query.phrase,
        "operator": query.operator.value,
        "speaker_refs": list(query.speaker_refs),
        "languages": list(query.languages),
        "document_ids": list(query.document_ids),
        "sort": query.sort.value,
        "limit": query.limit,
        "retrieval_mode": intent.mode.value,
        "context_segments": intent.context_segments,
        "tags": list(intent.filters.tags),
        "collections": list(intent.filters.collections),
        "note_text": intent.filters.note_text,
        "with_notes": intent.filters.with_notes,
    }


def _serialize_saved(saved: SavedSearch) -> dict[str, object]:
    return {
        "saved_search_id": saved.saved_search_id,
        "name": saved.name,
        "description": saved.description,
        "intent": _serialize_intent(
            ResearchSearchIntent.from_saved_intent(saved.intent)
        ),
        "created_at": saved.created_at,
        "updated_at": saved.updated_at,
    }


def _serialize_search(
    intent: ResearchSearchIntent,
    response: WorkspaceSearchResponse,
) -> dict[str, object]:
    retrieval = response.navigation.retrieval
    semantic_profile = retrieval.semantic_profile
    return {
        "intent": _serialize_intent(intent),
        "retrieval": {
            "mode": retrieval.mode.value,
            "lexical_backend_id": retrieval.lexical_backend_id,
            "semantic_backend_id": retrieval.semantic_backend_id,
            "fusion_profile": retrieval.fusion_profile,
            "semantic_profile": (
                None
                if semantic_profile is None
                else {
                    "model_id": semantic_profile.model_id,
                    "resolved_revision": semantic_profile.resolved_revision,
                    "dimensions": semantic_profile.dimensions,
                }
            ),
        },
        "evidence": [serialize_workspace_passage(item) for item in response.results],
    }


def dispatch_research_search(
    method: str,
    params: dict[str, object],
    workspace: ResearchWorkspaceService,
) -> object:
    """Dispatch typed search operations after the outer bridge allowlist accepts them."""
    service = ResearchSearchControlService(workspace)
    if method == "workspace.research.search.execute":
        execute_params = _ExecuteParams.model_validate(params)
        intent = execute_params.intent.to_intent()
        return _serialize_search(intent, service.search(intent))
    if method == "workspace.research.search.saved.list":
        list_params = _ListSavedParams.model_validate(params)
        return [
            _serialize_saved(saved)
            for saved in service.list_saved_searches(limit=list_params.limit)
        ]
    if method == "workspace.research.search.saved.create":
        create_params = _CreateSavedParams.model_validate(params)
        intent = create_params.intent.to_intent()
        return _serialize_saved(
            service.create_saved_search(
                create_params.name,
                intent,
                description=create_params.description,
            )
        )
    if method == "workspace.research.search.saved.inspect":
        inspect_params = _SavedIdentifierParams.model_validate(params)
        return _serialize_saved(
            service.inspect_saved_search(inspect_params.saved_search_id)
        )
    if method == "workspace.research.search.saved.replace":
        replace_params = _ReplaceSavedParams.model_validate(params)
        intent = replace_params.intent.to_intent()
        return _serialize_saved(
            service.replace_saved_search(
                replace_params.saved_search_id,
                name=replace_params.name,
                description=replace_params.description,
                intent=intent,
                expected_updated_at=replace_params.expected_updated_at,
            )
        )
    if method == "workspace.research.search.saved.run":
        run_params = _SavedIdentifierParams.model_validate(params)
        saved, response = service.run_saved_search(run_params.saved_search_id)
        intent = ResearchSearchIntent.from_saved_intent(saved.intent)
        return _serialize_search(intent, response)
    if method == "workspace.research.search.saved.delete":
        delete_params = _DeleteSavedParams.model_validate(params)
        service.delete_saved_search(
            delete_params.saved_search_id,
            expected_updated_at=delete_params.expected_updated_at,
        )
        return {"saved_search_id": delete_params.saved_search_id, "deleted": True}
    raise ValueError("Unsupported typed Research search desktop method")