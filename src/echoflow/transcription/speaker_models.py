"""Domain values for anonymous, recording-scoped speaker diarization."""

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SpeakerTurn:
    """One source-relative interval attributed to an anonymous speaker."""

    start_seconds: float
    end_seconds: float
    speaker_ref: str

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.start_seconds)
            or not math.isfinite(self.end_seconds)
            or self.start_seconds < 0
            or self.end_seconds <= self.start_seconds
        ):
            raise ValueError("speaker-turn timestamps must be finite and ordered")
        if not self.speaker_ref.strip():
            raise ValueError("speaker_ref cannot be empty")

    def to_dict(self) -> dict[str, object]:
        return {
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "speaker_ref": self.speaker_ref,
        }


@dataclass(frozen=True, slots=True)
class DiarizationProvenance:
    """Explain which local diarization implementation produced speaker turns."""

    provider: str
    package_version: str
    model: str
    model_revision: str | None
    mode: str = "anonymous_turns_v1"
    telemetry_enabled: bool = False

    def __post_init__(self) -> None:
        for name in ("provider", "package_version", "model", "mode"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} cannot be empty")
        if self.model_revision is not None and not self.model_revision.strip():
            raise ValueError("model_revision cannot be empty")
        if self.telemetry_enabled:
            raise ValueError("EchoFlow diarization telemetry must remain disabled")

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "package_version": self.package_version,
            "model": self.model,
            "model_revision": self.model_revision,
            "mode": self.mode,
            "telemetry_enabled": self.telemetry_enabled,
        }


@dataclass(frozen=True, slots=True)
class SpeakerDiarizationRequest:
    """Optional user knowledge that can constrain anonymous speaker counting."""

    num_speakers: int | None = None
    min_speakers: int | None = None
    max_speakers: int | None = None

    def __post_init__(self) -> None:
        for name in ("num_speakers", "min_speakers", "max_speakers"):
            value = getattr(self, name)
            if value is not None and value < 1:
                raise ValueError(f"{name} must be positive")
        if self.num_speakers is not None and (
            self.min_speakers is not None or self.max_speakers is not None
        ):
            raise ValueError(
                "num_speakers cannot be combined with speaker-count bounds"
            )
        if (
            self.min_speakers is not None
            and self.max_speakers is not None
            and self.min_speakers > self.max_speakers
        ):
            raise ValueError("min_speakers cannot exceed max_speakers")

    def kwargs(self) -> dict[str, int]:
        values = {
            "num_speakers": self.num_speakers,
            "min_speakers": self.min_speakers,
            "max_speakers": self.max_speakers,
        }
        return {name: value for name, value in values.items() if value is not None}


@dataclass(frozen=True, slots=True)
class SpeakerDiarizationResult:
    turns: tuple[SpeakerTurn, ...]
    provenance: DiarizationProvenance

    def __post_init__(self) -> None:
        if tuple(sorted(self.turns, key=_turn_sort_key)) != self.turns:
            raise ValueError("speaker turns must be sorted deterministically")


def _turn_sort_key(turn: SpeakerTurn) -> tuple[float, float, str]:
    return (turn.start_seconds, turn.end_seconds, turn.speaker_ref)
