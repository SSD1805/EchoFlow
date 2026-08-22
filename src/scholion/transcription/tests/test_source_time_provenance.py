from scholion.media.models import (
    InputIdentity,
    MediaInfo,
    MediaStream,
    MediaTemporalTag,
    StreamKind,
    TemporalTagKind,
    TemporalTagSource,
)
from scholion.runner.models import ProcessingProfile
from scholion.transcription.models import (
    CanonicalTranscript,
    DecodeStrategy,
    EngineProvenance,
    TranscriptSource,
)


def media(tmp_path, *, temporal_tags=()):
    source = tmp_path / "interview.mov"
    return MediaInfo(
        input=InputIdentity(source, 42, 7, "a" * 64),
        container_format="mov,mp4,m4a,3gp,3g2,mj2",
        duration_seconds=5_000.0,
        streams=(MediaStream(1, StreamKind.AUDIO, "aac", 5_000.0),),
        primary_audio_stream_index=1,
        temporal_tags=temporal_tags,
    )


def test_temporal_metadata_is_provenance_not_checkpoint_source_identity(tmp_path):
    tag = MediaTemporalTag(
        TemporalTagKind.TIMECODE,
        "10:00:00:00",
        TemporalTagSource.STREAM,
        stream_index=1,
    )
    plain = TranscriptSource.from_media(media(tmp_path))
    tagged = TranscriptSource.from_media(media(tmp_path, temporal_tags=(tag,)))

    assert plain == tagged
    assert plain.to_dict() == tagged.to_dict()
    assert "temporal_tags" not in tagged.to_dict()


def test_canonical_transcript_preserves_source_declared_temporal_metadata(tmp_path):
    tags = (
        MediaTemporalTag(
            TemporalTagKind.TIMECODE,
            "10:00:00:00",
            TemporalTagSource.STREAM,
            stream_index=1,
        ),
        MediaTemporalTag(
            TemporalTagKind.CREATION_TIME,
            "2026-04-05T12:34:56Z",
            TemporalTagSource.FORMAT,
        ),
    )
    transcript = CanonicalTranscript(
        job_id="job-time",
        source=TranscriptSource.from_media(media(tmp_path, temporal_tags=tags)),
        profile=ProcessingProfile.BALANCED,
        provisional=False,
        decode_strategy=DecodeStrategy.DIRECT,
        engine=EngineProvenance(
            name="faster-whisper",
            package_version="1.2.1",
            model="small",
            model_revision="revision-1",
            device="cpu",
            compute_type="int8",
            cpu_threads=2,
            beam_size=5,
            requested_language=None,
        ),
        detected_language=None,
        language_probability=None,
        segments=(),
    )

    source = transcript.to_dict()["source"]
    assert isinstance(source, dict)
    assert source["temporal_tags"] == [tag.to_dict() for tag in tags]


def test_canonical_transcript_omits_empty_temporal_metadata_for_wire_compatibility(
    tmp_path,
):
    transcript = CanonicalTranscript(
        job_id="job-time",
        source=TranscriptSource.from_media(media(tmp_path)),
        profile=ProcessingProfile.BALANCED,
        provisional=False,
        decode_strategy=DecodeStrategy.DIRECT,
        engine=EngineProvenance(
            name="faster-whisper",
            package_version="1.2.1",
            model="small",
            model_revision="revision-1",
            device="cpu",
            compute_type="int8",
            cpu_threads=2,
            beam_size=5,
            requested_language=None,
        ),
        detected_language=None,
        language_probability=None,
        segments=(),
    )

    source = transcript.to_dict()["source"]
    assert isinstance(source, dict)
    assert "temporal_tags" not in source
