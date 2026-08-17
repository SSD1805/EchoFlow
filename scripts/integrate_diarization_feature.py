from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(relative: str, old: str, new: str) -> None:
    path = ROOT / relative
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one anchor in {relative}, found {count}")
    path.write_text(text.replace(old, new, 1))


def append_once(relative: str, marker: str, addition: str) -> None:
    path = ROOT / relative
    text = path.read_text()
    if addition.strip() in text:
        raise RuntimeError(f"addition already present in {relative}")
    if marker not in text:
        raise RuntimeError(f"marker missing in {relative}")
    path.write_text(text.replace(marker, f"{marker}{addition}", 1))


# Canonical schema v3 is opt-in: ordinary transcripts retain the schema-v2 wire shape.
replace_once(
    "src/echoflow/transcription/models.py",
    "from echoflow.runner.models import ExecutionPolicy, ProcessingProfile, RunnerResources\nfrom echoflow.workspace.models import Artifact, Job\n",
    "from echoflow.runner.models import ExecutionPolicy, ProcessingProfile, RunnerResources\n"
    "from echoflow.transcription.speaker_models import (\n"
    "    DiarizationProvenance,\n"
    "    SpeakerTurn,\n"
    ")\n"
    "from echoflow.workspace.models import Artifact, Job\n",
)
replace_once(
    "src/echoflow/transcription/models.py",
    "    schema_version: int = 2\n    detected_languages: tuple[str, ...] = ()\n    language_attribution: LanguageAttributionProvenance | None = None\n",
    "    schema_version: int = 2\n"
    "    detected_languages: tuple[str, ...] = ()\n"
    "    language_attribution: LanguageAttributionProvenance | None = None\n"
    "    speaker_turns: tuple[SpeakerTurn, ...] = ()\n"
    "    diarization: DiarizationProvenance | None = None\n",
)
replace_once(
    "src/echoflow/transcription/models.py",
    "        self._validate_core_contract()\n        derived_languages = self._derived_languages()\n",
    "        self._validate_core_contract()\n"
    "        self._validate_diarization_contract()\n"
    "        derived_languages = self._derived_languages()\n",
)
replace_once(
    "src/echoflow/transcription/models.py",
    "        if self.schema_version != 2:\n            raise ValueError(\"unsupported transcript schema version\")\n",
    "        if self.schema_version not in {2, 3}:\n"
    "            raise ValueError(\"unsupported transcript schema version\")\n",
)
replace_once(
    "src/echoflow/transcription/models.py",
    "    def _derived_languages(self) -> tuple[str, ...]:\n",
    "    def _validate_diarization_contract(self) -> None:\n"
    "        if self.schema_version == 2:\n"
    "            if self.diarization is not None or self.speaker_turns:\n"
    "                raise ValueError(\n"
    "                    \"speaker diarization requires transcript schema version 3\"\n"
    "                )\n"
    "            return\n"
    "        if self.diarization is None:\n"
    "            raise ValueError(\"schema version 3 requires diarization provenance\")\n"
    "        if any(\n"
    "            turn.end_seconds > self.source.duration_seconds + 1e-6\n"
    "            for turn in self.speaker_turns\n"
    "        ):\n"
    "            raise ValueError(\"speaker turn exceeds source duration\")\n"
    "        known_speakers = {turn.speaker_ref for turn in self.speaker_turns}\n"
    "        for segment in self.segments:\n"
    "            if (\n"
    "                segment.speaker_ref is not None\n"
    "                and segment.speaker_ref not in known_speakers\n"
    "            ):\n"
    "                raise ValueError(\n"
    "                    \"segment speaker_ref must come from diarization turns\"\n"
    "                )\n\n"
    "    def _derived_languages(self) -> tuple[str, ...]:\n",
)
old_to_dict = '''    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "source": self.source.to_dict(),
            "profile": self.profile.value,
            "provisional": self.provisional,
            "decode_strategy": self.decode_strategy.value,
            "engine": self.engine.to_dict(),
            "detected_language": self.detected_language,
            "detected_languages": list(self.detected_languages),
            "language_probability": self.language_probability,
            "language_attribution": (
                None
                if self.language_attribution is None
                else self.language_attribution.to_dict()
            ),
            "text": self.text,
            "segments": [segment.to_dict() for segment in self.segments],
        }
'''
new_to_dict = '''    def to_dict(self) -> dict[str, object]:
        document: dict[str, object] = {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "source": self.source.to_dict(),
            "profile": self.profile.value,
            "provisional": self.provisional,
            "decode_strategy": self.decode_strategy.value,
            "engine": self.engine.to_dict(),
            "detected_language": self.detected_language,
            "detected_languages": list(self.detected_languages),
            "language_probability": self.language_probability,
            "language_attribution": (
                None
                if self.language_attribution is None
                else self.language_attribution.to_dict()
            ),
            "text": self.text,
            "segments": [segment.to_dict() for segment in self.segments],
        }
        if self.schema_version == 3:
            document["diarization"] = self.diarization.to_dict() if self.diarization else None
            document["speaker_turns"] = [turn.to_dict() for turn in self.speaker_turns]
        return document
'''
replace_once("src/echoflow/transcription/models.py", old_to_dict, new_to_dict)

# Executor: diarization is an optional final enrichment over canonical decoded audio.
replace_once(
    "src/echoflow/transcription/executor.py",
    "from echoflow.transcription.checkpoint import RestoredCheckpoint\nfrom echoflow.transcription.errors import CheckpointError, ResourceAdmissionError\n",
    "from echoflow.transcription.checkpoint import RestoredCheckpoint\n"
    "from echoflow.transcription.diarization import project_speaker_refs\n"
    "from echoflow.transcription.errors import (\n"
    "    CheckpointError,\n"
    "    DiarizationDependencyError,\n"
    "    ResourceAdmissionError,\n"
    ")\n",
)
replace_once(
    "src/echoflow/transcription/executor.py",
    "from echoflow.transcription.segmentation import MaterializedAudioSegment\n",
    "from echoflow.transcription.segmentation import MaterializedAudioSegment\n"
    "from echoflow.transcription.speaker_models import (\n"
    "    SpeakerDiarizationRequest,\n"
    "    SpeakerDiarizationResult,\n"
    ")\n",
)
replace_once(
    "src/echoflow/transcription/executor.py",
    "class _NoCheckpointStore:\n",
    "class SpeakerDiarizer(Protocol):\n"
    "    def diarize(\n"
    "        self,\n"
    "        audio_path: Path,\n"
    "        *,\n"
    "        allow_model_download: bool,\n"
    "        request: SpeakerDiarizationRequest | None = None,\n"
    "    ) -> SpeakerDiarizationResult: ...\n\n\n"
    "class _NoCheckpointStore:\n",
)
replace_once(
    "src/echoflow/transcription/executor.py",
    "        language_attributor: TranscriptLanguageAttributor | None = None,\n        observer: ExecutionObserver | None = None,\n",
    "        language_attributor: TranscriptLanguageAttributor | None = None,\n"
    "        speaker_diarizer: SpeakerDiarizer | None = None,\n"
    "        observer: ExecutionObserver | None = None,\n",
)
replace_once(
    "src/echoflow/transcription/executor.py",
    "        self.language_attributor = language_attributor\n        self.observer = observer or NoOpExecutionObserver()\n",
    "        self.language_attributor = language_attributor\n"
    "        self.speaker_diarizer = speaker_diarizer\n"
    "        self.observer = observer or NoOpExecutionObserver()\n",
)
replace_once(
    "src/echoflow/transcription/executor.py",
    "        allow_model_download: bool = False,\n        resume: bool = False,\n    ) -> TranscriptionExecutionResult:\n",
    "        allow_model_download: bool = False,\n"
    "        resume: bool = False,\n"
    "        diarization_request: SpeakerDiarizationRequest | None = None,\n"
    "    ) -> TranscriptionExecutionResult:\n",
)
replace_once(
    "src/echoflow/transcription/executor.py",
    "            with self.observer.span(\"transcript.canonicalize\"):\n                transcript = self._transcript(plan, engine_result)\n",
    "            speaker_result: SpeakerDiarizationResult | None = None\n"
    "            if diarization_request is not None:\n"
    "                if self.speaker_diarizer is None:\n"
    "                    raise DiarizationDependencyError(\n"
    "                        \"Speaker diarization is not configured\"\n"
    "                    )\n"
    "                with self.observer.span(\"speaker.diarize\"):\n"
    "                    speaker_result = self.speaker_diarizer.diarize(\n"
    "                        decoded.path,\n"
    "                        allow_model_download=allow_model_download,\n"
    "                        request=diarization_request,\n"
    "                    )\n"
    "            with self.observer.span(\"transcript.canonicalize\"):\n"
    "                transcript = self._transcript(plan, engine_result, speaker_result)\n",
)
replace_once(
    "src/echoflow/transcription/executor.py",
    "    def _transcript(\n        self, plan: TranscriptionJobPlan, result: EngineTranscript\n    ) -> CanonicalTranscript:\n        segments, attribution = self._attribute_languages(result.segments)\n",
    "    def _transcript(\n"
    "        self,\n"
    "        plan: TranscriptionJobPlan,\n"
    "        result: EngineTranscript,\n"
    "        speaker_result: SpeakerDiarizationResult | None = None,\n"
    "    ) -> CanonicalTranscript:\n"
    "        segments, attribution = self._attribute_languages(result.segments)\n"
    "        if speaker_result is not None:\n"
    "            segments = project_speaker_refs(segments, speaker_result.turns)\n",
)
replace_once(
    "src/echoflow/transcription/executor.py",
    "            language_attribution=attribution,\n            segments=segments,\n        )\n",
    "            language_attribution=attribution,\n"
    "            segments=segments,\n"
    "            schema_version=3 if speaker_result is not None else 2,\n"
    "            speaker_turns=() if speaker_result is None else speaker_result.turns,\n"
    "            diarization=None if speaker_result is None else speaker_result.provenance,\n"
    "        )\n",
)

# Configuration and composition root. Credentials remain in HF's standard credential
# handling; EchoFlow stores only model identity/revision and private cache location.
replace_once(
    "src/echoflow/core/config.py",
    "    FASTER_WHISPER_MODEL_REVISION: str | None = Field(\n"
    "        default=None,\n"
    "        min_length=1,\n"
    "        description=\"Optional immutable model revision requested from the model hub\",\n"
    "    )\n",
    "    FASTER_WHISPER_MODEL_REVISION: str | None = Field(\n"
    "        default=None,\n"
    "        min_length=1,\n"
    "        description=\"Optional immutable model revision requested from the model hub\",\n"
    "    )\n"
    "    PYANNOTE_MODEL_ID: str = Field(\n"
    "        default=\"pyannote/speaker-diarization-community-1\",\n"
    "        min_length=1,\n"
    "        description=\"Optional local speaker-diarization model identifier\",\n"
    "    )\n"
    "    PYANNOTE_MODEL_REVISION: str | None = Field(\n"
    "        default=None,\n"
    "        min_length=1,\n"
    "        description=\"Optional immutable pyannote model revision\",\n"
    "    )\n",
)
replace_once(
    "src/echoflow/app/app_container.py",
    "from echoflow.transcription.checkpoint import LocalCheckpointStore\n",
    "from echoflow.transcription.checkpoint import LocalCheckpointStore\n"
    "from echoflow.transcription.diarization import PyannoteSpeakerDiarizer\n",
)
replace_once(
    "src/echoflow/app/app_container.py",
    "def _create_audio_decoder(config: AppConfig) -> FfmpegAudioDecoder:\n"
    "    return FfmpegAudioDecoder(timeout_seconds=config.FFMPEG_PROCESS_TIMEOUT_SECONDS)\n\n\n",
    "def _create_audio_decoder(config: AppConfig) -> FfmpegAudioDecoder:\n"
    "    return FfmpegAudioDecoder(timeout_seconds=config.FFMPEG_PROCESS_TIMEOUT_SECONDS)\n\n\n"
    "def _create_speaker_diarizer(config: AppConfig) -> PyannoteSpeakerDiarizer:\n"
    "    return PyannoteSpeakerDiarizer(\n"
    "        model_cache_path=config.MODEL_DIR / \"pyannote\",\n"
    "        model_id=config.PYANNOTE_MODEL_ID,\n"
    "        model_revision=config.PYANNOTE_MODEL_REVISION,\n"
    "    )\n\n\n",
)
replace_once(
    "src/echoflow/app/app_container.py",
    "    language_attributor = providers.Singleton(LinguaLanguageAttributor)\n",
    "    language_attributor = providers.Singleton(LinguaLanguageAttributor)\n"
    "    speaker_diarizer = providers.Factory(_create_speaker_diarizer, config=config)\n",
)
replace_once(
    "src/echoflow/app/app_container.py",
    "        language_attributor=language_attributor,\n        logger=logger,\n",
    "        language_attributor=language_attributor,\n"
    "        speaker_diarizer=speaker_diarizer,\n"
    "        logger=logger,\n",
)

# CLI: diarization is explicit and can optionally be constrained by known speaker count.
replace_once(
    "src/echoflow/cli.py",
    "from echoflow.transcription.models import (\n"
    "    TranscriptionExecutionResult,\n"
    "    TranscriptionJobPlan,\n"
    ")\n",
    "from echoflow.transcription.models import (\n"
    "    TranscriptionExecutionResult,\n"
    "    TranscriptionJobPlan,\n"
    ")\n"
    "from echoflow.transcription.speaker_models import SpeakerDiarizationRequest\n",
)
replace_once(
    "src/echoflow/cli.py",
    "    export_formats: list[TranscriptExportFormat] | None,\n) -> None:\n",
    "    export_formats: list[TranscriptExportFormat] | None,\n"
    "    diarize: bool,\n"
    "    speakers: int | None,\n"
    "    min_speakers: int | None,\n"
    "    max_speakers: int | None,\n"
    ") -> None:\n",
)
replace_once(
    "src/echoflow/cli.py",
    "    if dry_run and export_formats:\n        raise typer.BadParameter(\"--export cannot be combined with --dry-run\")\n\n\n",
    "    if dry_run and export_formats:\n"
    "        raise typer.BadParameter(\"--export cannot be combined with --dry-run\")\n"
    "    if dry_run and diarize:\n"
    "        raise typer.BadParameter(\"--diarize cannot be combined with --dry-run\")\n"
    "    if not diarize and any(\n"
    "        value is not None for value in (speakers, min_speakers, max_speakers)\n"
    "    ):\n"
    "        raise typer.BadParameter(\n"
    "            \"speaker-count options require --diarize\"\n"
    "        )\n\n\n"
    "def _diarization_request(\n"
    "    *,\n"
    "    enabled: bool,\n"
    "    speakers: int | None,\n"
    "    min_speakers: int | None,\n"
    "    max_speakers: int | None,\n"
    ") -> SpeakerDiarizationRequest | None:\n"
    "    if not enabled:\n"
    "        return None\n"
    "    try:\n"
    "        return SpeakerDiarizationRequest(\n"
    "            num_speakers=speakers,\n"
    "            min_speakers=min_speakers,\n"
    "            max_speakers=max_speakers,\n"
    "        )\n"
    "    except ValueError as exc:\n"
    "        raise typer.BadParameter(str(exc)) from exc\n\n\n",
)
replace_once(
    "src/echoflow/cli.py",
    "    allow_model_download: bool,\n    resume: bool,\n) -> TranscriptionExecutionResult:\n",
    "    allow_model_download: bool,\n"
    "    resume: bool,\n"
    "    diarization_request: SpeakerDiarizationRequest | None,\n"
    ") -> TranscriptionExecutionResult:\n",
)
replace_once(
    "src/echoflow/cli.py",
    "            resume=True,\n        )\n    return executor.execute(plan, allow_model_download=allow_model_download)\n",
    "            resume=True,\n"
    "            diarization_request=diarization_request,\n"
    "        )\n"
    "    return executor.execute(\n"
    "        plan,\n"
    "        allow_model_download=allow_model_download,\n"
    "        diarization_request=diarization_request,\n"
    "    )\n",
)
replace_once(
    "src/echoflow/cli.py",
    "    resume: Annotated[\n",
    "    diarize: Annotated[\n"
    "        bool,\n"
    "        typer.Option(\n"
    "            \"--diarize\",\n"
    "            help=\"Add anonymous local speaker turns and conservative speaker labels.\",\n"
    "        ),\n"
    "    ] = False,\n"
    "    speakers: Annotated[\n"
    "        int | None,\n"
    "        typer.Option(\n"
    "            \"--speakers\",\n"
    "            min=1,\n"
    "            help=\"Known exact speaker count for diarization.\",\n"
    "        ),\n"
    "    ] = None,\n"
    "    min_speakers: Annotated[\n"
    "        int | None,\n"
    "        typer.Option(\"--min-speakers\", min=1, help=\"Minimum expected speakers.\"),\n"
    "    ] = None,\n"
    "    max_speakers: Annotated[\n"
    "        int | None,\n"
    "        typer.Option(\"--max-speakers\", min=1, help=\"Maximum expected speakers.\"),\n"
    "    ] = None,\n"
    "    resume: Annotated[\n",
)
replace_once(
    "src/echoflow/cli.py",
    "            export_formats=export_formats,\n        )\n        container = _container(context)\n",
    "            export_formats=export_formats,\n"
    "            diarize=diarize,\n"
    "            speakers=speakers,\n"
    "            min_speakers=min_speakers,\n"
    "            max_speakers=max_speakers,\n"
    "        )\n"
    "        speaker_request = _diarization_request(\n"
    "            enabled=diarize,\n"
    "            speakers=speakers,\n"
    "            min_speakers=min_speakers,\n"
    "            max_speakers=max_speakers,\n"
    "        )\n"
    "        container = _container(context)\n",
)
replace_once(
    "src/echoflow/cli.py",
    "                resume=resume is not None,\n            )\n",
    "                resume=resume is not None,\n"
    "                diarization_request=speaker_request,\n"
    "            )\n",
)
replace_once(
    "src/echoflow/cli.py",
    "        (\"Segments\", str(len(transcript.segments))),\n    ]\n",
    "        (\"Segments\", str(len(transcript.segments))),\n"
    "        (\"Speakers\", str(len({turn.speaker_ref for turn in transcript.speaker_turns}))),\n"
    "    ]\n",
)

# Optional dependency: keep PyTorch/pyannote out of ordinary transcription installs.
replace_once(
    "pyproject.toml",
    "transcription = [\n    \"faster-whisper>=1.2.1,<2\",\n    \"lingua-language-detector>=2,<3\",\n]\n",
    "transcription = [\n"
    "    \"faster-whisper>=1.2.1,<2\",\n"
    "    \"lingua-language-detector>=2,<3\",\n"
    "]\n"
    "diarization = [\n"
    "    \"pyannote-audio>=4,<5\",\n"
    "]\n",
)
replace_once(
    "pyproject.toml",
    "    \"src/echoflow/transcription/language.py\",\n",
    "    \"src/echoflow/transcription/language.py\",\n"
    "    \"src/echoflow/transcription/diarization.py\",\n"
    "    \"src/echoflow/transcription/speaker_models.py\",\n",
)

print("diarization integration patches applied")
