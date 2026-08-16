from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from enum import StrEnum

from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.transcription.errors import TranscriptionError
from echoflow.transcription.models import CanonicalTranscript, RecognizedSegment
from echoflow.workspace.models import Artifact, ArtifactKind, Job
from echoflow.workspace.service import WorkspaceService


class TranscriptExportError(TranscriptionError):
    """A canonical transcript could not be rendered or published safely."""


class TranscriptExportFormat(StrEnum):
    TEXT = "txt"
    SUBRIP = "srt"
    WEBVTT = "vtt"

    @property
    def artifact_kind(self) -> ArtifactKind:
        return {
            TranscriptExportFormat.TEXT: ArtifactKind.TEXT,
            TranscriptExportFormat.SUBRIP: ArtifactKind.SUBRIP,
            TranscriptExportFormat.WEBVTT: ArtifactKind.WEBVTT,
        }[self]


@dataclass(frozen=True, slots=True)
class TranscriptExportResult:
    artifacts: tuple[Artifact, ...]

    def to_dict(self) -> list[dict[str, str]]:
        return [artifact.to_dict() for artifact in self.artifacts]


def _milliseconds(seconds: float, *, end: bool) -> int:
    value = Decimal(str(seconds)) * 1000
    rounding = ROUND_CEILING if end else ROUND_FLOOR
    return int(value.to_integral_value(rounding=rounding))


def _timestamp(seconds: float, *, separator: str, end: bool) -> str:
    total_ms = _milliseconds(seconds, end=end)
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return (
        f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}"
        f"{separator}{milliseconds:03d}"
    )


def _cue_text(segment: RecognizedSegment) -> str:
    if "\x00" in segment.text:
        raise TranscriptExportError("Transcript contains text that cannot be exported")
    normalized = segment.text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in normalized.split("\n") if line.strip()]
    if not lines:
        raise TranscriptExportError("Transcript contains an empty subtitle cue")
    return " ".join(lines)


def render_text(transcript: CanonicalTranscript) -> bytes:
    return f"{transcript.text}\n".encode()


def render_subrip(transcript: CanonicalTranscript) -> bytes:
    blocks: list[str] = []
    for cue_number, segment in enumerate(transcript.segments, start=1):
        start = _timestamp(segment.start_seconds, separator=",", end=False)
        end = _timestamp(segment.end_seconds, separator=",", end=True)
        blocks.append(f"{cue_number}\n{start} --> {end}\n{_cue_text(segment)}")
    document = "\n\n".join(blocks)
    return (f"{document}\n\n" if document else "").encode()


def render_webvtt(transcript: CanonicalTranscript) -> bytes:
    blocks: list[str] = []
    for segment in transcript.segments:
        start = _timestamp(segment.start_seconds, separator=".", end=False)
        end = _timestamp(segment.end_seconds, separator=".", end=True)
        blocks.append(
            f"{segment.segment_id}\n{start} --> {end}\n{_cue_text(segment)}"
        )
    body = "\n\n".join(blocks)
    return ("WEBVTT\n\n" + (f"{body}\n\n" if body else "")).encode()


def render_transcript(
    transcript: CanonicalTranscript, export_format: TranscriptExportFormat
) -> bytes:
    renderers = {
        TranscriptExportFormat.TEXT: render_text,
        TranscriptExportFormat.SUBRIP: render_subrip,
        TranscriptExportFormat.WEBVTT: render_webvtt,
    }
    return renderers[export_format](transcript)


class TranscriptExporter:
    """Publish deterministic views without making them transcript authorities."""

    def __init__(
        self,
        *,
        workspace_service: WorkspaceService,
        file_manager: FileManagerFacade,
    ):
        self.workspace_service = workspace_service
        self.file_manager = file_manager

    def publish(
        self,
        job: Job,
        transcript: CanonicalTranscript,
        formats: tuple[TranscriptExportFormat, ...],
    ) -> TranscriptExportResult:
        selected = tuple(dict.fromkeys(formats))
        payloads = tuple(
            (export_format, render_transcript(transcript, export_format))
            for export_format in selected
        )
        reserved: list[tuple[Artifact, bytes]] = []
        try:
            for export_format, payload in payloads:
                artifact = self.workspace_service.reserve_artifact(
                    job, export_format.artifact_kind
                )
                reserved.append((artifact, payload))
            for artifact, payload in reserved:
                self.file_manager.save_file(payload, artifact.path)
        except BaseException:
            for artifact, _ in reserved:
                with suppress(Exception):
                    self.file_manager.delete_file(artifact.path)
            raise
        return TranscriptExportResult(tuple(artifact for artifact, _ in reserved))
