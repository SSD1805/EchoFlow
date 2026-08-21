# Verified native playback

EchoFlow can play the original local audio or video from a verified transcript coordinate without turning the webview into a filesystem client.

Playback is deliberately evidence-bound. A browser media element is not allowed to decide that a path, transcript generation, source file, or audio track is trustworthy. Python verifies those facts first, Rust opens the authorized file and owns the resulting native capability, and React receives only an opaque session plus safe playback coordinates.

## What playback proves

A playback request carries only:

- `document_id`;
- the exact `canonical_sha256` already attached to the evidence view; and
- a finite non-negative source-relative seek coordinate.

Before granting playback, Python verifies that:

1. the requested transcript generation is still the indexed generation;
2. the canonical JSON bytes still hash to that generation;
3. canonical job/source identity still agrees with the library index;
4. the remembered original source still exists;
5. FFprobe can inspect the source using EchoFlow's file-only media policy;
6. the current source SHA-256 and size still match canonical provenance;
7. the requested coordinate is inside the verified recording duration; and
8. the source has exactly one audio stream and that stream is the one recorded by canonical evidence.

A stale view, changed file, missing file, incompatible canonical generation, invalid coordinate, or ambiguous audio-track situation fails closed.

## Why multi-audio playback is refused for now

Canonical evidence records which audio stream EchoFlow transcribed. A generic WebView media element does not give EchoFlow a portable guarantee that it will render that same audio track from every multi-track container.

Playing a different track while presenting transcript evidence would be a provenance error, not merely a UX inconvenience. Therefore first-release playback rejects sources with more than one audio stream instead of guessing. A future multi-track playback implementation must make track selection explicit and verifiable at the native media layer before this restriction can be relaxed.

This restriction is **playback-specific**. EchoFlow already supports transcription from a file with several embedded audio streams. Processing Center requires an explicit user choice when preflight discovers multiple tracks, Python re-plans with that exact stream index, FFmpeg maps only that stream into canonical working audio, canonical source provenance records the index, and resume restores it. See **[Audio tracks](audio-tracks.md)**.

The distinction is intentional: transcription owns extraction and can prove which stream entered ASR; current WebView playback of the original container cannot yet prove which embedded stream the platform media engine rendered.

## Authority split

```text
Evidence view
    │ document_id + canonical_sha256 + seek_seconds
    ▼
Python PlaybackAuthorizationService
    │ verifies canonical generation + source bytes + stream identity
    │ trusted grant includes source path
    ▼
Rust/Tauri native host
    │ opens file immediately and rechecks size/mtime
    │ stores opened File behind opaque active session ID
    ▼
echoflow-media protocol
    │ GET/HEAD only, active session IDs only, bounded byte ranges
    ▼
React <audio>/<video>
    safe URL token + duration + seek + media kind only
```

The Python playback bridge is intentionally not registered as a Tauri command. Only the fixed Rust playback command can call it. The raw trusted grant contains the local source path so Rust can open the file, but that object never crosses into the webview.

## Native media sessions

Rust turns an authorized source into an in-memory session backed by an already-open file handle.

The session contract is intentionally narrow:

- opaque IDs use a closed token shape, not paths;
- at most eight sessions may be active at once;
- only `GET` and `HEAD` are accepted by the media protocol;
- random, expired, malformed, or path-like tokens return no media;
- multipart ranges are rejected;
- each response body is capped at 1 MiB;
- responses use `Cache-Control: no-store`;
- release removes the session and closes the capability when no references remain.

The webview CSP allows media only from EchoFlow's dedicated `echoflow-media` protocol (including its platform-specific localhost representation). It does not add general `file:`, `blob:`, or arbitrary localhost media access.

## Time coordinates

Playback uses the same source-relative coordinate already produced by verified evidence navigation. Word buttons, the evidence-position control, and native media time all update one presentation cursor. React does not calculate transcript/source alignment.

Preparing playback verifies the source at the current cursor. There is no re-hash on every seek. This keeps ordinary scrubbing and native media transport lightweight while preserving a strong authorization boundary at session creation.

Older research anchors use the same rule. If a note cites an older canonical generation, playback authorization receives that exact generation identity. EchoFlow never silently substitutes the current transcript.

## Missing, moved, or changed recordings

Canonical transcript evidence remains valid when the original media is temporarily unavailable. Playback is a separate capability and fails with an explicit message.

If a recording has moved, refresh/reconnect the library location so the indexed source path points to the same verified bytes. EchoFlow does not search the machine heuristically during playback. If bytes changed at the remembered path, playback refuses the source even when the filename is unchanged.

## Codec support

Authorization proves identity, not decoder availability. The operating-system WebView ultimately decodes the authorized media container/codecs. A source can therefore be verified correctly but still be unplayable on a particular system media engine.

EchoFlow reports that as a decoder limitation. It does not transcode or replace the source silently during playback, because doing so would introduce another derived-media/provenance contract that should be designed explicitly.

## Performance

Playback authorization hashes and probes one source once when a session is prepared or explicitly re-verified. For very large recordings this can be visible I/O, but it is intentionally outside the high-frequency seek path.

The native protocol then serves bounded byte ranges from the already-open file. React does not read canonical JSON, stream files through Python, or poll Python during playback.

If representative-device profiling later shows authorization hashing to be a material bottleneck, the correct optimization is a generation/source-keyed verified backend cache with explicit invalidation. The webview must not become the cache authority.

## Qualification

Playback is covered at multiple layers:

- Python positive, negative, boundary, tamper, stale-generation, source-mismatch, stream-ambiguity, and Hypothesis seek tests;
- Python trusted-bridge allowlist, invalid JSON, extra-field, error-redaction, and request-size tests;
- Rust range-parser, token-allowlist, unknown-session, and bounded-stream tests executed in CI;
- Playwright current/older generation, exact word-coordinate, missing/changed/multi-audio, audio/video, keyboard, path-nondisclosure, and axe tests; and
- a targeted Poodle workflow that runs when playback authorization/bridge policy changes.

Multi-track transcription has separate backend probe/serialization/confirmation tests plus a Processing Center Playwright/axe flow that proves Start stays disabled until the backend-bound stream choice is confirmed.

The normal quality pipeline still enforces strict TypeScript, frontend build/audit, Ruff, mypy, Vulture, complexity reporting, dependency audit, Python branch coverage, Rust compilation/tests, platform smoke tests, packaging checks, and Playwright.
