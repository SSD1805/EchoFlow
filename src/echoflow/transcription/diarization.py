"""Optional local anonymous speaker diarization and conservative ASR fusion."""

import os
import re
from collections.abc import Callable
from dataclasses import replace
from importlib import import_module, metadata
from pathlib import Path
from typing import Any, cast

from echoflow.transcription.errors import (
    DiarizationDependencyError,
    DiarizationError,
    DiarizationModelUnavailableError,
)
from echoflow.transcription.models import RecognizedSegment
from echoflow.transcription.speaker_models import (
    DiarizationProvenance,
    SpeakerDiarizationRequest,
    SpeakerDiarizationResult,
    SpeakerTurn,
)

SnapshotLoader = Callable[..., str]
ModuleLoader = Callable[[str], Any]
VersionReader = Callable[[str], str]

# CVE-2026-58659 affects Lightning releases through 2.6.5. The upstream fix was
# merged in July 2026 but had not yet shipped in a normal 2.x release when this
# guard was added. Fail closed before importing pyannote, which subclasses
# LightningModule and loads model checkpoints through Lightning.
_MINIMUM_SAFE_LIGHTNING = (2, 6, 6)
_STABLE_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:\.post\d+)?$")


class PyannoteSpeakerDiarizer:
    """Run a locally cached pyannote pipeline with telemetry forced off.

    Model acquisition is performed through Hugging Face Hub's snapshot API so
    ``allow_model_download=False`` can enforce cache-only behavior. The pyannote
    pipeline itself receives a local snapshot path and therefore never needs an HF
    credential during inference.
    """

    def __init__(
        self,
        *,
        model_cache_path: Path,
        model_id: str = "pyannote/speaker-diarization-community-1",
        model_revision: str | None = None,
        snapshot_loader: SnapshotLoader | None = None,
        module_loader: ModuleLoader = import_module,
        version_reader: VersionReader = metadata.version,
    ) -> None:
        if not model_id.strip():
            raise ValueError("model_id cannot be empty")
        if model_revision is not None and not model_revision.strip():
            raise ValueError("model_revision cannot be empty")
        self.model_cache_path = model_cache_path.expanduser().resolve(strict=False)
        self.model_id = model_id
        self.model_revision = model_revision
        self._snapshot_loader = snapshot_loader
        self._module_loader = module_loader
        self._version_reader = version_reader

    def diarize(
        self,
        audio_path: Path,
        *,
        allow_model_download: bool,
        request: SpeakerDiarizationRequest | None = None,
    ) -> SpeakerDiarizationResult:
        """Return deterministic anonymous turns for one canonical local audio file."""
        # Prove the optional runtime is safe and installed before model resolution.
        # This prevents both needless gated downloads and execution of a known
        # vulnerable Lightning checkpoint loader.
        pyannote = self._load_pyannote()
        local_model = self._resolve_model(allow_model_download=allow_model_download)
        try:
            pipeline = pyannote.Pipeline.from_pretrained(local_model)
            if pipeline is None:
                raise DiarizationModelUnavailableError(
                    "The local diarization model could not be loaded"
                )
            output = pipeline(
                str(audio_path), **(request or SpeakerDiarizationRequest()).kwargs()
            )
            raw_turns = tuple(output.speaker_diarization)
        except DiarizationModelUnavailableError:
            raise
        except Exception as exc:
            raise DiarizationError(
                "Local speaker diarization failed", cause=exc
            ) from exc

        turns = self._normalize_turns(raw_turns)
        return SpeakerDiarizationResult(
            turns=turns,
            provenance=DiarizationProvenance(
                provider="pyannote.audio",
                package_version=self._version_reader("pyannote-audio"),
                model=self.model_id,
                model_revision=self.model_revision,
            ),
        )

    def _resolve_model(self, *, allow_model_download: bool) -> str:
        loader = self._snapshot_loader
        if loader is None:
            try:
                hub = self._module_loader("huggingface_hub")
                loader = hub.snapshot_download
            except (ImportError, AttributeError) as exc:
                raise DiarizationDependencyError(
                    "Speaker diarization dependencies are not installed", cause=exc
                ) from exc
        try:
            return loader(
                repo_id=self.model_id,
                revision=self.model_revision,
                cache_dir=str(self.model_cache_path),
                local_files_only=not allow_model_download,
            )
        except Exception as exc:
            action = (
                "download or access"
                if allow_model_download
                else "find in the local cache"
            )
            raise DiarizationModelUnavailableError(
                f"Could not {action} the speaker diarization model",
                cause=exc,
            ) from exc

    def _load_pyannote(self) -> Any:
        # Set the upstream-documented disable value before importing pyannote so
        # EchoFlow never emits pyannote usage metrics by default.
        os.environ["PYANNOTE_METRICS_ENABLED"] = "0"
        self._require_safe_lightning()
        try:
            return self._module_loader("pyannote.audio")
        except ImportError as exc:
            raise DiarizationDependencyError(
                "Speaker diarization dependencies are not installed", cause=exc
            ) from exc

    def _require_safe_lightning(self) -> None:
        try:
            version = self._version_reader("lightning")
        except metadata.PackageNotFoundError as exc:
            raise DiarizationDependencyError(
                "Speaker diarization dependencies are not installed", cause=exc
            ) from exc
        match = _STABLE_VERSION.fullmatch(version)
        if match is None:
            raise DiarizationDependencyError(
                "Speaker diarization is blocked because the installed Lightning "
                "release cannot be proven safe for checkpoint loading"
            )
        parsed = tuple(int(component) for component in match.groups())
        if parsed < _MINIMUM_SAFE_LIGHTNING:
            raise DiarizationDependencyError(
                "Speaker diarization is temporarily blocked because the installed "
                "Lightning release is affected by CVE-2026-58659"
            )

    @staticmethod
    def _normalize_turns(raw_turns: tuple[object, ...]) -> tuple[SpeakerTurn, ...]:
        parsed: list[tuple[float, float, str]] = []
        for item in raw_turns:
            try:
                turn, raw_speaker = cast(tuple[Any, Any], item)
                start = float(turn.start)
                end = float(turn.end)
                label = str(raw_speaker)
            except (AttributeError, TypeError, ValueError) as exc:
                raise DiarizationError(
                    "Diarization returned invalid speaker turns", cause=exc
                ) from exc
            parsed.append((start, end, label))
        parsed.sort(key=lambda item: (item[0], item[1], item[2]))

        speaker_map: dict[str, str] = {}
        normalized: list[SpeakerTurn] = []
        for start, end, label in parsed:
            if label not in speaker_map:
                speaker_map[label] = f"speaker-{len(speaker_map) + 1:02d}"
            normalized.append(SpeakerTurn(start, end, speaker_map[label]))
        return tuple(normalized)


def project_speaker_refs(
    segments: tuple[RecognizedSegment, ...],
    turns: tuple[SpeakerTurn, ...],
) -> tuple[RecognizedSegment, ...]:
    """Attach a speaker only when one unique diarized speaker overlaps a segment.

    The exact speaker-turn timeline remains the primary diarization evidence. A text
    segment that crosses a speaker change or overlapping speech stays unattributed
    until a finer alignment capability can split the text defensibly.
    """
    projected: list[RecognizedSegment] = []
    for segment in segments:
        if segment.speaker_ref is not None:
            raise ValueError("speaker projection refuses to overwrite existing labels")
        speakers = {
            turn.speaker_ref for turn in turns if _overlap_seconds(segment, turn) > 0
        }
        speaker_ref = next(iter(speakers)) if len(speakers) == 1 else None
        projected.append(replace(segment, speaker_ref=speaker_ref))
    return tuple(projected)


def _overlap_seconds(segment: RecognizedSegment, turn: SpeakerTurn) -> float:
    return max(
        0.0,
        min(segment.end_seconds, turn.end_seconds)
        - max(segment.start_seconds, turn.start_seconds),
    )
