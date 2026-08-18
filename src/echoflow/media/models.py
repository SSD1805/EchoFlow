import math
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class StreamKind(StrEnum):
    AUDIO = "audio"
    VIDEO = "video"
    SUBTITLE = "subtitle"
    DATA = "data"
    ATTACHMENT = "attachment"
    UNKNOWN = "unknown"


class TemporalTagKind(StrEnum):
    """Kinds of original-container temporal metadata EchoFlow preserves verbatim."""

    TIMECODE = "timecode"
    CREATION_TIME = "creation_time"


class TemporalTagSource(StrEnum):
    """Where FFprobe reported one original-media temporal tag."""

    FORMAT = "format"
    STREAM = "stream"


@dataclass(frozen=True, slots=True)
class MediaTemporalTag:
    """One source-declared temporal fact, preserved without claiming it is true."""

    kind: TemporalTagKind
    value: str
    source: TemporalTagSource
    stream_index: int | None = None

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        if not normalized:
            raise ValueError("temporal tag value cannot be empty")
        object.__setattr__(self, "value", normalized)
        if self.source is TemporalTagSource.FORMAT and self.stream_index is not None:
            raise ValueError("format temporal tags cannot have a stream index")
        if self.source is TemporalTagSource.STREAM and (
            self.stream_index is None or self.stream_index < 0
        ):
            raise ValueError("stream temporal tags require a nonnegative stream index")

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "value": self.value,
            "source": self.source.value,
            "stream_index": self.stream_index,
        }


@dataclass(frozen=True, slots=True)
class InputIdentity:
    path: Path
    size_bytes: int
    modified_ns: int
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", self.path.expanduser().resolve(strict=False))
        if self.size_bytes < 1:
            raise ValueError("size_bytes must be positive")
        if self.modified_ns < 0:
            raise ValueError("modified_ns cannot be negative")
        if not _SHA256_PATTERN.fullmatch(self.sha256):
            raise ValueError("sha256 must be a lowercase 64-character digest")

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "size_bytes": self.size_bytes,
            "modified_ns": self.modified_ns,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class MediaStream:
    index: int
    kind: StreamKind
    codec: str
    duration_seconds: float | None = None
    sample_rate_hz: int | None = None
    channels: int | None = None
    channel_layout: str | None = None
    bit_rate_bps: int | None = None

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("stream index cannot be negative")
        if not self.codec:
            raise ValueError("stream codec cannot be empty")
        if self.duration_seconds is not None and (
            not math.isfinite(self.duration_seconds) or self.duration_seconds < 0
        ):
            raise ValueError("stream duration must be finite and nonnegative")
        for name in ("sample_rate_hz", "channels", "bit_rate_bps"):
            value = getattr(self, name)
            if value is not None and value < 1:
                raise ValueError(f"{name} must be positive")

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "kind": self.kind.value,
            "codec": self.codec,
            "duration_seconds": self.duration_seconds,
            "sample_rate_hz": self.sample_rate_hz,
            "channels": self.channels,
            "channel_layout": self.channel_layout,
            "bit_rate_bps": self.bit_rate_bps,
        }


@dataclass(frozen=True, slots=True)
class MediaInfo:
    input: InputIdentity
    container_format: str
    duration_seconds: float
    streams: tuple[MediaStream, ...]
    primary_audio_stream_index: int
    temporal_tags: tuple[MediaTemporalTag, ...] = ()

    def __post_init__(self) -> None:
        if not self.container_format:
            raise ValueError("container_format cannot be empty")
        if not math.isfinite(self.duration_seconds) or self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be finite and positive")
        if not self.streams:
            raise ValueError("streams cannot be empty")
        selected = [
            stream
            for stream in self.streams
            if stream.index == self.primary_audio_stream_index
            and stream.kind is StreamKind.AUDIO
        ]
        if len(selected) != 1:
            raise ValueError("primary_audio_stream_index must select one audio stream")
        stream_indices = {stream.index for stream in self.streams}
        if any(
            tag.source is TemporalTagSource.STREAM
            and tag.stream_index not in stream_indices
            for tag in self.temporal_tags
        ):
            raise ValueError("stream temporal tag must reference a discovered stream")

    @property
    def primary_audio_stream(self) -> MediaStream:
        return next(
            stream
            for stream in self.streams
            if stream.index == self.primary_audio_stream_index
        )

    def to_dict(self) -> dict[str, object]:
        document: dict[str, object] = {
            "input": self.input.to_dict(),
            "container_format": self.container_format,
            "duration_seconds": self.duration_seconds,
            "streams": [stream.to_dict() for stream in self.streams],
            "primary_audio_stream_index": self.primary_audio_stream_index,
        }
        if self.temporal_tags:
            document["temporal_tags"] = [tag.to_dict() for tag in self.temporal_tags]
        return document
