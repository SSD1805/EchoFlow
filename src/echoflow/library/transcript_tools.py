"""Application-owned transcript inspection, speaker management, and publication."""

from __future__ import annotations

import hashlib
import json
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from echoflow.core.errors import StorageAlreadyExistsError
from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.library.errors import SpeakerLabelStateError, TranscriptToolingError
from echoflow.library.index import IndexedDocument, TranscriptIndex
from echoflow.library.speaker_label_service import (
    SpeakerLabelService,
    SpeakerRosterEntry,
)
from echoflow.library.speaker_presentation import (
    SpeakerPresentationService,
    SpeakerPresentationSpan,
)
from echoflow.transcription.export import (
    TranscriptExportFormat,
    TranscriptRenderSegment,
    render_transcript_parts,
)

_MAX_CANONICAL_BYTES = 256 * 1024 * 1024
_MAX_COLLISION_ATTEMPTS = 1_000


class _CanonicalSource(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(gt=0)
    modified_ns: int = Field(ge=0)
    container_format: str = Field(min_length=1)
    duration_seconds: float = Field(gt=0)
    audio_stream_index: int = Field(ge=0)


class _CanonicalEngine(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1)
    package_version: str = Field(min_length=1)
    model: str = Field(min_length=1)
    model_revision: str = Field(min_length=1)
    device: str = Field(min_length=1)
    compute_type: str = Field(min_length=1)


class _CanonicalDiarization(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: str = Field(min_length=1)
    package_version: str = Field(min_length=1)
    model: str = Field(min_length=1)
    model_revision: str | None = Field(default=None, min_length=1)
    mode: str = Field(min_length=1)


class _CanonicalEnhancement(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: str = Field(min_length=1)
    provider_version: str = Field(min_length=1)
    operation: str = Field(min_length=1)
    model_id: str | None = Field(default=None, min_length=1)
    model_revision: str | None = Field(default=None, min_length=1)


class _CanonicalSegment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    segment_id: str = Field(min_length=1)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    text: str = Field(min_length=1)
    speaker_ref: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_timing(self) -> _CanonicalSegment:
        if self.end_seconds < self.start_seconds:
            raise ValueError("canonical segment timestamps must be ordered")
        return self


class _CanonicalSpeakerTurn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    speaker_ref: str = Field(min_length=1)


class _CanonicalTranscriptProjection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: int
    job_id: str
    source: _CanonicalSource
    profile: str
    provisional: bool
    decode_strategy: str
    engine: _CanonicalEngine
    detected_language: str | None = None
    detected_languages: list[str] = Field(default_factory=list)
    segments: list[_CanonicalSegment]
    diarization: _CanonicalDiarization | None = None
    speaker_turns: list[_CanonicalSpeakerTurn] = Field(default_factory=list)
    enhancement: _CanonicalEnhancement | None = None


@dataclass(frozen=True, slots=True)
class TranscriptEngineDetails:
    name: str
    package_version: str
    model: str
    model_revision: str
    device: str
    compute_type: str


@dataclass(frozen=True, slots=True)
class TranscriptDiarizationDetails:
    provider: str
    package_version: str
    model: str
    model_revision: str | None
    mode: str


@dataclass(frozen=True, slots=True)
class TranscriptEnhancementDetails:
    provider: str
    provider_version: str
    operation: str
    model_id: str | None
    model_revision: str | None


@dataclass(frozen=True, slots=True)
class TranscriptDetails:
    document_id: str
    source_sha256: str
    canonical_sha256: str
    source_available: bool
    source_size_bytes: int
    source_modified_ns: int
    container_format: str
    duration_seconds: float
    audio_stream_index: int
    profile: str
    provisional: bool
    decode_strategy: str
    detected_language: str | None
    detected_languages: tuple[str, ...]
    segment_count: int
    speaker_count: int
    engine: TranscriptEngineDetails
    diarization: TranscriptDiarizationDetails | None
    enhancement: TranscriptEnhancementDetails | None


@dataclass(frozen=True, slots=True)
class TranscriptToolingSnapshot:
    details: TranscriptDetails
    speakers: tuple[SpeakerRosterEntry, ...]


@dataclass(frozen=True, slots=True)
class TranscriptPublication:
    format: TranscriptExportFormat
    filename: str


@dataclass(frozen=True, slots=True)
class TranscriptPublicationResult:
    canonical_sha256: str
    publications: tuple[TranscriptPublication, ...]


class TranscriptToolsService:
    """Keep transcript-tool policy in Python and expose only typed results to adapters."""

    def __init__(
        self,
        *,
        index: TranscriptIndex,
        speaker_labels: SpeakerLabelService,
        speaker_presentation: SpeakerPresentationService,
        file_manager: FileManagerFacade,
    ) -> None:
        self.index = index
        self.speaker_labels = speaker_labels
        self.speaker_presentation = speaker_presentation
        self.file_manager = file_manager

    def inspect(
        self,
        document_id: str,
        *,
        expected_canonical_sha256: str,
    ) -> TranscriptToolingSnapshot:
        document, projection = self._verified_projection(
            document_id,
            expected_canonical_sha256=expected_canonical_sha256,
        )
        try:
            speakers = self.speaker_labels.roster(
                document_id, expected_canonical_sha256=expected_canonical_sha256
            )
        except SpeakerLabelStateError as exc:
            raise TranscriptToolingError(exc.public_message, cause=exc) from exc
        details = self._details(
            document, expected_canonical_sha256, projection, speaker_count=len(speakers)
        )
        return TranscriptToolingSnapshot(details=details, speakers=speakers)

    def speaker_spans(
        self,
        document_id: str,
        *,
        expected_canonical_sha256: str,
    ) -> tuple[SpeakerPresentationSpan, ...]:
        self._require_generation(document_id, expected_canonical_sha256)
        try:
            spans = self.speaker_presentation.spans(document_id)
        except SpeakerLabelStateError as exc:
            raise TranscriptToolingError(exc.public_message, cause=exc) from exc
        if any(span.canonical_sha256 != expected_canonical_sha256 for span in spans):
            raise TranscriptToolingError(
                "Transcript changed while speaker presentation was being prepared; reopen it"
            )
        return spans

    def set_speaker_label(
        self,
        document_id: str,
        *,
        expected_canonical_sha256: str,
        speaker_ref: str,
        label: str,
    ) -> SpeakerRosterEntry:
        self._require_generation(document_id, expected_canonical_sha256)
        try:
            binding = self.speaker_labels.set_label(
                document_id,
                speaker_ref=speaker_ref,
                label=label,
                expected_canonical_sha256=expected_canonical_sha256,
            )
        except SpeakerLabelStateError as exc:
            raise TranscriptToolingError(exc.public_message, cause=exc) from exc
        if binding.canonical_sha256 != expected_canonical_sha256:
            raise TranscriptToolingError(
                "Transcript changed while the speaker name was being saved; reopen it"
            )
        return SpeakerRosterEntry(
            speaker_ref=binding.speaker_ref,
            display_label=binding.label,
        )

    def remove_speaker_label(
        self,
        document_id: str,
        *,
        expected_canonical_sha256: str,
        speaker_ref: str,
    ) -> bool:
        self._require_generation(document_id, expected_canonical_sha256)
        try:
            return self.speaker_labels.remove_label(
                document_id,
                speaker_ref=speaker_ref,
                expected_canonical_sha256=expected_canonical_sha256,
            )
        except SpeakerLabelStateError as exc:
            raise TranscriptToolingError(exc.public_message, cause=exc) from exc

    def publish(
        self,
        document_id: str,
        *,
        expected_canonical_sha256: str,
        destination: str | Path,
        formats: tuple[TranscriptExportFormat, ...],
    ) -> TranscriptPublicationResult:
        document, projection = self._verified_projection(
            document_id,
            expected_canonical_sha256=expected_canonical_sha256,
        )
        selected = tuple(dict.fromkeys(formats))
        if not selected:
            raise ValueError("select at least one transcript export format")

        output_dir = Path(destination).expanduser().resolve(strict=False)
        if not output_dir.is_dir():
            raise TranscriptToolingError(
                "Selected export destination is not an available folder"
            )

        segments = tuple(
            TranscriptRenderSegment(
                segment_id=segment.segment_id,
                start_seconds=segment.start_seconds,
                end_seconds=segment.end_seconds,
                text=segment.text,
                speaker_ref=segment.speaker_ref,
            )
            for segment in projection.segments
        )
        transcript_text = " ".join(
            segment.text.strip() for segment in projection.segments
        )
        payloads = tuple(
            (
                export_format,
                render_transcript_parts(transcript_text, segments, export_format),
            )
            for export_format in selected
        )

        stem = self._publication_stem(document)
        reserved: list[tuple[TranscriptPublication, Path, bytes]] = []
        try:
            for export_format, payload in payloads:
                path = self._reserve_publication(
                    output_dir,
                    f"{stem}.{export_format.value}",
                )
                reserved.append(
                    (
                        TranscriptPublication(
                            format=export_format,
                            filename=path.name,
                        ),
                        path,
                        payload,
                    )
                )
            for _, path, payload in reserved:
                self.file_manager.save_file(payload, path)
        except BaseException:
            for _, path, _ in reserved:
                with suppress(Exception):
                    self.file_manager.delete_file(path)
            raise

        return TranscriptPublicationResult(
            canonical_sha256=expected_canonical_sha256,
            publications=tuple(item for item, _, _ in reserved),
        )

    def _details(
        self,
        document: IndexedDocument,
        canonical_sha256: str,
        projection: _CanonicalTranscriptProjection,
        *,
        speaker_count: int,
    ) -> TranscriptDetails:
        engine = projection.engine
        diarization = projection.diarization
        enhancement = projection.enhancement
        return TranscriptDetails(
            document_id=document.document_id,
            source_sha256=projection.source.sha256,
            canonical_sha256=canonical_sha256,
            source_available=(
                document.source_path is not None
                and self.file_manager.file_exists(Path(document.source_path))
            ),
            source_size_bytes=projection.source.size_bytes,
            source_modified_ns=projection.source.modified_ns,
            container_format=projection.source.container_format,
            duration_seconds=projection.source.duration_seconds,
            audio_stream_index=projection.source.audio_stream_index,
            profile=projection.profile,
            provisional=projection.provisional,
            decode_strategy=projection.decode_strategy,
            detected_language=projection.detected_language,
            detected_languages=tuple(projection.detected_languages),
            segment_count=len(projection.segments),
            speaker_count=speaker_count,
            engine=TranscriptEngineDetails(
                name=engine.name,
                package_version=engine.package_version,
                model=engine.model,
                model_revision=engine.model_revision,
                device=engine.device,
                compute_type=engine.compute_type,
            ),
            diarization=(
                None
                if diarization is None
                else TranscriptDiarizationDetails(
                    provider=diarization.provider,
                    package_version=diarization.package_version,
                    model=diarization.model,
                    model_revision=diarization.model_revision,
                    mode=diarization.mode,
                )
            ),
            enhancement=(
                None
                if enhancement is None
                else TranscriptEnhancementDetails(
                    provider=enhancement.provider,
                    provider_version=enhancement.provider_version,
                    operation=enhancement.operation,
                    model_id=enhancement.model_id,
                    model_revision=enhancement.model_revision,
                )
            ),
        )

    def _verified_projection(
        self,
        document_id: str,
        *,
        expected_canonical_sha256: str,
    ) -> tuple[IndexedDocument, _CanonicalTranscriptProjection]:
        document = self._require_generation(document_id, expected_canonical_sha256)
        try:
            path = Path(document.canonical_path)
            metadata = self.file_manager.get_file_metadata(path)
            if metadata["size"] > _MAX_CANONICAL_BYTES:
                raise TranscriptToolingError(
                    "Canonical transcript is too large to inspect safely in the desktop"
                )
            payload = self.file_manager.read_file(path)
            if hashlib.sha256(payload).hexdigest() != expected_canonical_sha256:
                raise TranscriptToolingError(
                    "Canonical transcript changed; rebuild the library before using transcript tools"
                )
            projection = _CanonicalTranscriptProjection.model_validate(
                json.loads(payload)
            )
            if projection.schema_version != 1:
                raise TranscriptToolingError(
                    "Canonical transcript uses an unsupported schema version"
                )
            if projection.source.sha256 != document.source_sha256:
                raise TranscriptToolingError(
                    "Canonical transcript source identity no longer matches the library index"
                )
            if projection.job_id != document.document_id:
                raise TranscriptToolingError(
                    "Canonical transcript identity no longer matches the library index"
                )
            if len(projection.segments) != document.segment_count:
                raise TranscriptToolingError(
                    "Canonical transcript segment count no longer matches the library index"
                )
            return document, projection
        except TranscriptToolingError:
            raise
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            ValidationError,
            ValueError,
        ) as exc:
            raise TranscriptToolingError(
                "Canonical transcript details could not be validated safely",
                cause=exc,
            ) from exc

    def _require_generation(
        self,
        document_id: str,
        expected_canonical_sha256: str,
    ) -> IndexedDocument:
        if len(expected_canonical_sha256) != 64 or any(
            character not in "0123456789abcdef"
            for character in expected_canonical_sha256
        ):
            raise ValueError(
                "expected_canonical_sha256 must be a lowercase 64-character digest"
            )
        document = next(
            (
                item
                for item in self.index.documents()
                if item.document_id == document_id
            ),
            None,
        )
        if document is None:
            raise TranscriptToolingError(
                "Transcript is not present in the local library"
            )
        if document.canonical_sha256 is None:
            raise TranscriptToolingError(
                "Transcript index predates canonical hashing; rebuild the library first"
            )
        if document.canonical_sha256 != expected_canonical_sha256:
            raise TranscriptToolingError(
                "Transcript changed since this view was opened; reopen it before making changes"
            )
        return document

    def _publication_stem(self, document: IndexedDocument) -> str:
        source_stem = (
            Path(document.source_path).stem
            if document.source_path is not None
            else document.document_id
        )
        stem = self.file_manager.sanitize_filename(source_stem).strip(" .")
        return stem or "transcript"

    def _reserve_publication(self, directory: Path, filename: str) -> Path:
        path = Path(filename)
        for index in range(1, _MAX_COLLISION_ATTEMPTS + 1):
            candidate = directory / (
                filename if index == 1 else f"{path.stem}-{index}{path.suffix}"
            )
            try:
                self.file_manager.reserve_file(candidate)
            except StorageAlreadyExistsError:
                continue
            return candidate
        raise TranscriptToolingError(
            "EchoFlow could not allocate a unique transcript export filename"
        )
