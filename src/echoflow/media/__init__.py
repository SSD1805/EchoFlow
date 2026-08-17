"""Local-media inspection and deterministic audio-stream selection.

The media package owns facts about the original container before transcription:
input identity/fingerprint, container duration, discovered streams, codec metadata,
and the selected audio-stream index. ``FfprobeMediaProbe`` is read-only inspection;
it does not transcode or normalize media. ``AudioStreamSelector`` chooses one of the
already-discovered audio streams without rewriting the probe result in place.

Actual extraction and canonical-audio normalization live at the transcription audio
boundary because they are execution work, not media discovery.
"""

from echoflow.media.models import InputIdentity, MediaInfo, MediaStream, StreamKind
from echoflow.media.probe import FfprobeMediaProbe
from echoflow.media.selection import AudioStreamSelector

__all__ = [
    "AudioStreamSelector",
    "FfprobeMediaProbe",
    "InputIdentity",
    "MediaInfo",
    "MediaStream",
    "StreamKind",
]
