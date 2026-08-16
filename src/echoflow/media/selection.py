from dataclasses import replace

from echoflow.media.errors import UnsupportedMediaError
from echoflow.media.models import MediaInfo, StreamKind


class AudioStreamSelector:
    """Select one deterministic audio stream without mutating probe metadata."""

    def select(
        self,
        media: MediaInfo,
        *,
        requested_index: int | None = None,
    ) -> MediaInfo:
        audio_streams = tuple(
            stream for stream in media.streams if stream.kind is StreamKind.AUDIO
        )
        if not audio_streams:
            raise UnsupportedMediaError("Input contains no audio stream")

        selected_index = (
            audio_streams[0].index if requested_index is None else requested_index
        )
        if not any(stream.index == selected_index for stream in audio_streams):
            raise UnsupportedMediaError("Requested audio stream is not available")

        if media.primary_audio_stream_index == selected_index:
            return media
        return replace(media, primary_audio_stream_index=selected_index)
