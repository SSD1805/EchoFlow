"""Compose ranked retrieval with verified canonical navigation and user display state."""

from __future__ import annotations

from dataclasses import dataclass

from echoflow.library.evidence import EvidenceLocation, EvidenceLocator
from echoflow.library.index import SearchQuery
from echoflow.library.retrieval import RetrievalMode, SearchPassage, SearchResponse
from echoflow.library.service import TranscriptLibraryService
from echoflow.library.speaker_label_service import SpeakerLabelService


@dataclass(frozen=True, slots=True)
class SpeakerDisplay:
    """Anonymous evidence reference plus optional user-authored presentation label."""

    speaker_ref: str
    display_label: str | None = None

    @property
    def display_name(self) -> str:
        if self.display_label is None:
            return self.speaker_ref
        return f"{self.display_label}\n{self.speaker_ref}"


@dataclass(frozen=True, slots=True)
class LocatedSearchPassage:
    """One ranked passage enriched with verified canonical navigation coordinates."""

    passage: SearchPassage
    evidence: EvidenceLocation
    speakers: tuple[SpeakerDisplay, ...]

    def __post_init__(self) -> None:
        if self.passage.document_id != self.evidence.document_id:
            raise ValueError("passage and evidence document identities must match")
        if self.passage.canonical_sha256 != self.evidence.canonical_sha256:
            raise ValueError("passage and evidence canonical identities must match")


@dataclass(frozen=True, slots=True)
class ResearchSearchResponse:
    """Retrieval provenance plus canonical navigation for every result."""

    retrieval: SearchResponse
    results: tuple[LocatedSearchPassage, ...]

    def __post_init__(self) -> None:
        if len(self.retrieval.results) != len(self.results):
            raise ValueError("research results must preserve retrieval result cardinality")
        if tuple(item.passage for item in self.results) != self.retrieval.results:
            raise ValueError("research results must preserve retrieval result order")


class ResearchNavigationService:
    """Make search results usable without changing ranking or canonical evidence."""

    def __init__(
        self,
        transcript_library: TranscriptLibraryService,
        evidence_locator: EvidenceLocator,
        speaker_labels: SpeakerLabelService,
    ) -> None:
        self.transcript_library = transcript_library
        self.evidence_locator = evidence_locator
        self.speaker_labels = speaker_labels

    def search(
        self,
        query: SearchQuery,
        *,
        mode: RetrievalMode = RetrievalMode.LEXICAL,
        context_segments: int = 0,
    ) -> ResearchSearchResponse:
        retrieval = self.transcript_library.retrieve(query, mode=mode)
        locations = self.evidence_locator.locate_response(
            retrieval,
            context_segments=context_segments,
        )

        requested: dict[tuple[str, str], set[str]] = {}
        for location in locations:
            key = (location.document_id, location.canonical_sha256)
            requested.setdefault(key, set()).update(location.result_speaker_refs)
        labels_by_generation: dict[tuple[str, str], dict[str, str]] = {}
        for key, refs in requested.items():
            document_id, canonical_sha256 = key
            labels_by_generation[key] = self.speaker_labels.display_labels(
                document_id=document_id,
                canonical_sha256=canonical_sha256,
                speaker_refs=tuple(sorted(refs)),
            )

        results = tuple(
            self._located(passage, location, labels_by_generation)
            for passage, location in zip(retrieval.results, locations, strict=True)
        )
        return ResearchSearchResponse(retrieval=retrieval, results=results)

    @staticmethod
    def _located(
        passage: SearchPassage,
        location: EvidenceLocation,
        labels_by_generation: dict[tuple[str, str], dict[str, str]],
    ) -> LocatedSearchPassage:
        labels = labels_by_generation.get(
            (location.document_id, location.canonical_sha256), {}
        )
        speakers = tuple(
            SpeakerDisplay(speaker_ref=ref, display_label=labels.get(ref))
            for ref in location.result_speaker_refs
        )
        return LocatedSearchPassage(
            passage=passage,
            evidence=location,
            speakers=speakers,
        )
