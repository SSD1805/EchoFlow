import hashlib
import json
import math
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from scholion.media.errors import (
    InputChangedError,
    MediaProbeError,
    MediaToolUnavailableError,
    UnsupportedMediaError,
)
from scholion.media.models import (
    InputIdentity,
    MediaInfo,
    MediaStream,
    MediaTemporalTag,
    StreamKind,
    TemporalTagKind,
    TemporalTagSource,
)

_HASH_BLOCK_SIZE = 1024 * 1024
_MAX_PROBE_OUTPUT_BYTES = 1024 * 1024
_MAX_STREAM_TITLE_LENGTH = 200
_MAX_STREAM_LANGUAGE_LENGTH = 64
_FFPROBE_ENTRIES = (
    "format=format_name,duration:format_tags=timecode,creation_time:"
    "stream=index,codec_type,codec_name,duration,sample_rate,channels,"
    "channel_layout,bit_rate:stream_tags=timecode,creation_time"
)
_FFPROBE_TRACK_DISPLAY_ENTRIES = (
    "stream=index:stream_tags=title,language:stream_disposition=default"
)


def _optional_int(value: object) -> int | None:
    try:
        parsed = int(str(value))
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _optional_float(value: object) -> float | None:
    try:
        parsed = float(str(value))
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) and parsed >= 0 else None


def _stream_kind(value: object) -> StreamKind:
    try:
        return StreamKind(str(value))
    except ValueError:
        return StreamKind.UNKNOWN


def _fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(_HASH_BLOCK_SIZE):
            digest.update(block)
    return digest.hexdigest()


def _snapshot(path: Path) -> tuple[int, int, int, int]:
    details = path.stat()
    return details.st_size, details.st_mtime_ns, details.st_dev, details.st_ino


def _tag_value(raw_tags: object, key: str) -> str | None:
    if not isinstance(raw_tags, dict):
        return None
    value = raw_tags.get(key)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _display_tag(raw_tags: object, key: str, maximum: int) -> str | None:
    value = _tag_value(raw_tags, key)
    if value is None:
        return None
    return value[:maximum]


def _default_disposition(raw_disposition: object) -> bool:
    if not isinstance(raw_disposition, dict):
        return False
    value = raw_disposition.get("default")
    if value is True:
        return True
    if isinstance(value, int):
        return value == 1
    if isinstance(value, str):
        return value == "1"
    return False


def _raw_stream_index(raw_stream: object) -> int | None:
    if not isinstance(raw_stream, dict):
        return None
    index = raw_stream.get("index")
    if isinstance(index, bool):
        return None
    try:
        return int(str(index))
    except (TypeError, ValueError):
        return None


def _multiple_audio_streams(payload: Mapping[str, Any]) -> bool:
    raw_streams = payload.get("streams")
    if not isinstance(raw_streams, list):
        return False
    audio_count = 0
    for stream in raw_streams:
        if not isinstance(stream, dict):
            continue
        codec_type = stream.get("codec_type")
        if isinstance(codec_type, str) and codec_type == "audio":
            audio_count += 1
            if audio_count > 1:
                return True
    return False


def _display_stream_lookup(payload: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    raw_streams = payload.get("streams")
    if not isinstance(raw_streams, list):
        return {}
    lookup: dict[int, Mapping[str, Any]] = {}
    for stream in raw_streams:
        index = _raw_stream_index(stream)
        if index is not None and isinstance(stream, dict):
            lookup[index] = stream
    return lookup


def _parse_stream(
    raw_stream: object,
    display_stream: Mapping[str, Any] | None = None,
) -> MediaStream:
    if not isinstance(raw_stream, dict):
        raise MediaProbeError("FFprobe stream metadata is invalid")
    index = raw_stream.get("index")
    try:
        if isinstance(index, bool):
            raise ValueError("boolean stream index")
        parsed_index = int(str(index))
    except (TypeError, ValueError) as exc:
        raise MediaProbeError("FFprobe stream index is invalid", cause=exc) from exc
    display_source = display_stream if display_stream is not None else raw_stream
    tags = display_source.get("tags")
    try:
        return MediaStream(
            index=parsed_index,
            kind=_stream_kind(raw_stream.get("codec_type")),
            codec=str(raw_stream.get("codec_name") or "unknown"),
            duration_seconds=_optional_float(raw_stream.get("duration")),
            sample_rate_hz=_optional_int(raw_stream.get("sample_rate")),
            channels=_optional_int(raw_stream.get("channels")),
            channel_layout=(
                str(raw_stream["channel_layout"])
                if raw_stream.get("channel_layout")
                else None
            ),
            bit_rate_bps=_optional_int(raw_stream.get("bit_rate")),
            title=_display_tag(tags, "title", _MAX_STREAM_TITLE_LENGTH),
            language=_display_tag(tags, "language", _MAX_STREAM_LANGUAGE_LENGTH),
            is_default=_default_disposition(display_source.get("disposition")),
        )
    except ValueError as exc:
        raise MediaProbeError(
            "FFprobe stream metadata failed validation", cause=exc
        ) from exc


def _audio_duration(
    raw_format: Mapping[str, Any], audio_streams: list[MediaStream]
) -> float:
    duration = _optional_float(raw_format.get("duration"))
    if duration is None or duration <= 0:
        stream_durations = [
            stream.duration_seconds
            for stream in audio_streams
            if stream.duration_seconds is not None
        ]
        duration = max(stream_durations, default=0.0)
    if duration <= 0:
        raise UnsupportedMediaError("Input audio duration could not be determined")
    return duration


def _temporal_tags(
    raw_format: Mapping[str, Any],
    raw_streams: list[object],
    streams: list[MediaStream],
) -> tuple[MediaTemporalTag, ...]:
    """Preserve temporal declarations without resolving conflicts or asserting truth."""
    tags: list[MediaTemporalTag] = []
    kinds = (
        (TemporalTagKind.TIMECODE, "timecode"),
        (TemporalTagKind.CREATION_TIME, "creation_time"),
    )

    format_tags = raw_format.get("tags")
    for kind, key in kinds:
        value = _tag_value(format_tags, key)
        if value is not None:
            tags.append(
                MediaTemporalTag(
                    kind=kind,
                    value=value,
                    source=TemporalTagSource.FORMAT,
                )
            )

    for raw_stream, stream in zip(raw_streams, streams, strict=True):
        if not isinstance(raw_stream, dict):
            continue
        stream_tags = raw_stream.get("tags")
        for kind, key in kinds:
            value = _tag_value(stream_tags, key)
            if value is not None:
                tags.append(
                    MediaTemporalTag(
                        kind=kind,
                        value=value,
                        source=TemporalTagSource.STREAM,
                        stream_index=stream.index,
                    )
                )
    return tuple(tags)


class FfprobeMediaProbe:
    """Fingerprint and inspect one local media file without network protocols."""

    def __init__(
        self,
        timeout_seconds: float = 10.0,
        max_output_bytes: int = _MAX_PROBE_OUTPUT_BYTES,
    ):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_output_bytes < 1:
            raise ValueError("max_output_bytes must be positive")
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes

    def probe(self, input_path: str | Path) -> MediaInfo:
        source = Path(input_path).expanduser().resolve(strict=False)
        try:
            before = _snapshot(source)
        except OSError as exc:
            raise MediaProbeError(
                "Input metadata could not be read", cause=exc
            ) from exc
        if before[0] < 1:
            raise UnsupportedMediaError("Input file is empty")

        executable = shutil.which("ffprobe")
        if executable is None:
            raise MediaToolUnavailableError(
                "FFprobe is required to inspect audio input"
            )

        payload = self._run(executable, source, entries=_FFPROBE_ENTRIES)
        display_lookup: Mapping[int, Mapping[str, Any]] = {}
        if _multiple_audio_streams(payload):
            display_payload = self._run(
                executable,
                source,
                entries=_FFPROBE_TRACK_DISPLAY_ENTRIES,
            )
            display_lookup = _display_stream_lookup(display_payload)
        try:
            sha256 = _fingerprint(source)
            after = _snapshot(source)
        except OSError as exc:
            raise MediaProbeError(
                "Input could not be fingerprinted", cause=exc
            ) from exc
        if before != after:
            raise InputChangedError("Input changed while it was being inspected")

        return self._parse(
            payload,
            InputIdentity(
                path=source,
                size_bytes=after[0],
                modified_ns=after[1],
                sha256=sha256,
            ),
            display_lookup=display_lookup,
        )

    def _run(
        self,
        executable: str,
        source: Path,
        *,
        entries: str = _FFPROBE_ENTRIES,
    ) -> Mapping[str, Any]:
        command = [
            executable,
            "-v",
            "error",
            "-protocol_whitelist",
            "file",
            "-show_entries",
            entries,
            "-of",
            "json",
            str(source),
        ]
        try:
            completed = subprocess.run(  # noqa: S603
                command,
                capture_output=True,
                check=False,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise MediaProbeError("Media inspection timed out", cause=exc) from exc
        except UnicodeError as exc:
            raise MediaProbeError(
                "FFprobe returned invalid metadata", cause=exc
            ) from exc
        except OSError as exc:
            raise MediaToolUnavailableError(
                "FFprobe could not be executed", cause=exc
            ) from exc
        if completed.returncode != 0:
            raise UnsupportedMediaError(
                "Input could not be inspected as supported local media"
            )
        if len(completed.stdout.encode("utf-8")) > self.max_output_bytes:
            raise MediaProbeError("Media metadata exceeded the safe inspection limit")
        try:
            payload = json.loads(completed.stdout)
        except (json.JSONDecodeError, UnicodeError) as exc:
            raise MediaProbeError(
                "FFprobe returned invalid metadata", cause=exc
            ) from exc
        if not isinstance(payload, dict):
            raise MediaProbeError("FFprobe returned invalid metadata")
        return payload

    @staticmethod
    def _parse(
        payload: Mapping[str, Any],
        identity: InputIdentity,
        *,
        display_lookup: Mapping[int, Mapping[str, Any]] | None = None,
    ) -> MediaInfo:
        raw_streams = payload.get("streams")
        raw_format = payload.get("format")
        if not isinstance(raw_streams, list) or not isinstance(raw_format, dict):
            raise MediaProbeError("FFprobe metadata is incomplete")

        track_display = display_lookup or {}
        streams: list[MediaStream] = []
        for raw_stream in raw_streams:
            stream_index = _raw_stream_index(raw_stream)
            display_stream = (
                track_display.get(stream_index) if stream_index is not None else None
            )
            streams.append(_parse_stream(raw_stream, display_stream))

        audio_streams = [
            stream for stream in streams if stream.kind is StreamKind.AUDIO
        ]
        if not audio_streams:
            raise UnsupportedMediaError("Input contains no audio stream")

        container_format = str(raw_format.get("format_name") or "unknown")
        try:
            return MediaInfo(
                input=identity,
                container_format=container_format,
                duration_seconds=_audio_duration(raw_format, audio_streams),
                streams=tuple(streams),
                primary_audio_stream_index=audio_streams[0].index,
                temporal_tags=_temporal_tags(raw_format, raw_streams, streams),
            )
        except ValueError as exc:
            raise MediaProbeError(
                "FFprobe metadata failed validation", cause=exc
            ) from exc
