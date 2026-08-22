# Audio tracks

A recording file can contain more than one embedded audio track. A video might carry a camera microphone and a clean lavalier feed; an archive file might contain several language tracks; a recorder may preserve a mix and isolated channels as separate streams.

Scholion treats **one file with multiple embedded audio streams** as one source recording with an explicit transcription-track choice. This is different from giving Scholion several separate files and asking it to synchronize them.

## Single-track recordings

If FFprobe finds exactly one audio stream, Scholion uses that stream. There is nothing useful for the user to choose.

The selected stream index is still recorded in the transcription source contract so canonical evidence can explain exactly which audio produced the transcript.

## Multi-track recordings in the desktop

When preflight finds more than one audio stream, Processing Center does not treat the first stream as user intent.

Instead it:

1. presents the available audio tracks in the ordinary preflight surface;
2. shows bounded source-declared track metadata when available, including title, language, codec, channel count, sample rate, and whether the container marked a stream as default;
3. requires the user to choose one track explicitly;
4. sends only that stream index back to Python;
5. re-runs backend preflight with the exact selected index; and
6. enables **Start local transcription** only after the backend returns a plan bound to that stream.

The chooser is not an audio-quality classifier. A label such as `Lav microphone`, `eng`, or `container default` came from the source container. Scholion shows that information to help a person recognize the track, but it does not claim the label is accurate or recommend a stream because of it.

Track title and language are bounded before they can enter the desktop DTO. They are display metadata, not filesystem authority, and they are not added to canonical source identity.

## Command line selection

The CLI already accepts an exact FFmpeg stream index:

```bash
uv run scholion transcribe meeting.mkv --audio-stream 3 --dry-run
uv run scholion transcribe meeting.mkv --audio-stream 3
```

Scholion validates that the requested index exists and is an audio stream. An unavailable or non-audio index fails instead of falling back to another track.

Use the dry-run plan to inspect the selected stream and other processing decisions before starting work.

## What is preserved as evidence

Canonical transcript source provenance records the exact `audio_stream_index` used for transcription. The stream index is part of the source/execution contract because it answers the evidentiary question: **which audio inside these source bytes produced this transcript?**

The source file SHA-256 and size still identify the recording bytes. Track title, language, and default-disposition metadata are descriptive source declarations and therefore do not replace or strengthen that cryptographic identity.

A checkpoint resume restores the original selected stream. It does not re-run current defaults or silently move to another track.

A fresh retry is different: it creates a new plan and may choose another track explicitly.

## Why multi-track transcription works while multi-track playback still refuses

These are different guarantees.

During transcription Scholion owns extraction. FFmpeg receives an explicit mapping for the selected stream and drops unrelated video, subtitle, data, and other audio streams from the canonical working-audio path. Scholion can therefore prove which track entered ASR.

Verified native playback currently hands the original container to the operating-system WebView media engine. Scholion does not yet have a portable native guarantee that every platform will render the same embedded audio stream recorded in canonical provenance.

Playing track 1 while displaying a transcript produced from track 3 would be an evidence error. For that reason verified playback currently refuses sources with multiple audio streams instead of guessing. See **[Verified native playback](native-playback.md)**.

A future relaxation must make native playback track selection explicit and verifiable. The desktop transcription chooser does not weaken that requirement.

## What this does not support

Scholion does **not** currently treat several separate files as synchronized tracks of one evidence object, for example:

```text
camera.wav
lav.wav
interpreter.wav
```

That would require a different evidence model covering source identity for every file, alignment offsets, clock drift, missing spans, resampling, and how one transcript cites several originals. It should be designed explicitly rather than hidden inside the embedded-stream feature.

For the underlying media/timeline model, see **[Media normalization and transcript timeline](architecture/media-and-timeline.md)**. For Processing Center ownership, see **[Processing Center](architecture/processing-center.md)**.
