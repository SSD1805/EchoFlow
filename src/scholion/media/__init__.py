"""Local-media inspection and deterministic audio-stream selection.

The media package owns facts about the original container before transcription:
input identity/fingerprint, container duration, discovered streams, codec metadata,
source-declared temporal metadata, and the selected audio-stream index.
``FfprobeMediaProbe`` is read-only inspection; it does not transcode or normalize media.
``AudioStreamSelector`` chooses one of the already-discovered audio streams without
rewriting the probe result in place.

Actual extraction and canonical-audio normalization live at the transcription audio
boundary because they are execution work, not media discovery. Human elapsed timestamp
formatting is presentation-only; canonical evidence remains numeric source-relative
seconds.
"""

from scholion.media.models import (
    InputIdentity,
    MediaInfo,
    MediaStream,
    MediaTemporalTag,
    StreamKind,
    TemporalTagKind,
    TemporalTagSource,
)
from scholion.media.probe import FfprobeMediaProbe
from scholion.media.selection import AudioStreamSelector
from scholion.media.time_coordinates import format_elapsed_timestamp

__all__ = [
    "AudioStreamSelector",
    "FfprobeMediaProbe",
    "InputIdentity",
    "MediaInfo",
    "MediaStream",
    "MediaTemporalTag",
    "StreamKind",
    "TemporalTagKind",
    "TemporalTagSource",
    "format_elapsed_timestamp",
]
