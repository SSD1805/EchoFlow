from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class EnhancementMode(StrEnum):
    OFF = "off"
    ON = "on"


def _validate_parameters(parameters: tuple[tuple[str, str], ...]) -> None:
    keys: set[str] = set()
    for key, value in parameters:
        if not key.strip() or not value.strip():
            raise ValueError("enhancement parameters cannot contain empty keys or values")
        if key in keys:
            raise ValueError("enhancement parameter keys must be unique")
        keys.add(key)


@dataclass(frozen=True, slots=True)
class EnhancementConfiguration:
    """Immutable preprocessing contract persisted with a transcription job."""

    mode: EnhancementMode = EnhancementMode.OFF
    provider: str | None = None
    parameters: tuple[tuple[str, str], ...] = ()
    model_id: str | None = None
    model_revision: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported enhancement schema version")
        _validate_parameters(self.parameters)
        if self.mode is EnhancementMode.OFF:
            if any(
                value is not None
                for value in (self.provider, self.model_id, self.model_revision)
            ) or self.parameters:
                raise ValueError("disabled enhancement cannot declare provider state")
            return
        if self.provider is None or not self.provider.strip():
            raise ValueError("enabled enhancement requires a provider")
        if self.model_id is not None and not self.model_id.strip():
            raise ValueError("enhancement model_id cannot be empty")
        if self.model_revision is not None and not self.model_revision.strip():
            raise ValueError("enhancement model_revision cannot be empty")
        if self.model_revision is not None and self.model_id is None:
            raise ValueError("enhancement model_revision requires model_id")

    @property
    def enabled(self) -> bool:
        return self.mode is EnhancementMode.ON

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "mode": self.mode.value,
            "provider": self.provider,
            "parameters": dict(self.parameters),
            "model_id": self.model_id,
            "model_revision": self.model_revision,
        }


@dataclass(frozen=True, slots=True)
class EnhancementProvenance:
    """Evidence describing the exact local preprocessing applied to ASR input."""

    provider: str
    provider_version: str
    operation: str
    parameters: tuple[tuple[str, str], ...]
    model_id: str | None = None
    model_revision: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported enhancement provenance schema version")
        for name in ("provider", "provider_version", "operation"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} cannot be empty")
        _validate_parameters(self.parameters)
        if self.model_id is not None and not self.model_id.strip():
            raise ValueError("enhancement provenance model_id cannot be empty")
        if self.model_revision is not None and not self.model_revision.strip():
            raise ValueError("enhancement provenance model_revision cannot be empty")
        if self.model_revision is not None and self.model_id is None:
            raise ValueError("enhancement provenance model_revision requires model_id")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "provider_version": self.provider_version,
            "operation": self.operation,
            "parameters": dict(self.parameters),
            "model_id": self.model_id,
            "model_revision": self.model_revision,
        }


@dataclass(frozen=True, slots=True)
class EnhancedAudio:
    """Private derived audio used only as downstream processing material."""

    path: Path
    provenance: EnhancementProvenance
    temporary: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", self.path.expanduser().resolve(strict=False))
