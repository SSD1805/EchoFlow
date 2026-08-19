# Durable library locations and recording discovery

EchoFlow lets a user work in two modes without confusing them:

1. **one-time selection** — choose particular recordings or canonical transcripts and do not remember the containing directory; and
2. **remembered locations** — explicitly grant EchoFlow permission to revisit a directory at later application lifecycle points.

Remembering a location is durable application preference state. It is not transcript evidence, research annotation state, or permission to copy/delete the user's source files.

## Custody and storage

Remembered locations are stored privately at:

```text
<STATE_DIR>/library/user-state/library-locations.json
```

The file is schema-versioned, validated fail-closed, written atomically through the shared file-manager boundary, and protected as private application state.

A location stores an absolute normalized path, a stable location ID, its purpose, enabled state, and recording-processing policy. EchoFlow does not copy the selected directory into private state.

The configured EchoFlow output directory is already an implicit transcript discovery root and therefore cannot be redundantly registered. Private state/cache/model directories cannot be registered as library locations.

## Location purposes

### Transcript library

A `transcript-library` location means:

> Revisit this directory when reconciling canonical transcript evidence.

At a refresh lifecycle point, enabled and currently available transcript roots are passed to the existing incremental `TranscriptLibraryService.refresh()` path. Missing roots, such as an unplugged external drive, are reported as unavailable but are not silently forgotten.

The existing custody rules remain unchanged:

- canonical JSON remains evidence authority;
- normal refresh uses metadata only as a cheap change detector;
- changed/new canonical bytes are validated and hashed before lexical mutation;
- semantic state is invalidated when corpus identity changes; and
- full rebuild remains a repair/recovery operation.

### Recording source

A `recording-source` location means:

> Revisit this directory to discover local recording candidates.

Discovery is intentionally cheap. EchoFlow enumerates ordinary audio/video filename candidates, records their path/size/location provenance, and does **not** open, hash, FFprobe, transcribe, copy, or modify them merely because they were discovered.

Media validation remains the responsibility of the existing transcription planner and FFprobe boundary when the user (or an explicitly authorized application workflow) actually plans processing.

Hidden files and unrelated extensions are ignored during cheap discovery. The first backend contract scans the selected directory itself rather than recursively walking arbitrary directory trees; a user may remember multiple roots. Recursive/watch behavior should be added only with explicit traversal, symlink, performance, and custody policy.

## Discovery is not processing

The central invariant is:

```text
remember location
      ↓
discover candidate
      ↓
NO ASR SIDE EFFECT
```

Recording sources have a durable processing policy:

- `manual` — default; discovery may surface candidates, but processing requires explicit user selection;
- `automatic` — explicit opt-in metadata indicating that a higher-level application adapter may submit newly discovered recordings for processing.

`automatic` does not itself start ASR. `LibraryLocationService.discover_recordings()` never calls the transcription planner or executor.

A future desktop lifecycle adapter that honors automatic processing must still:

1. define a clear trigger, such as application startup/refresh while EchoFlow is running;
2. avoid processing partially copied or unstable files;
3. use the normal transcription planner and resource admission path;
4. require required models to already be present unless a separate explicit network-bearing acquisition was authorized;
5. preserve resume/checkpoint semantics;
6. avoid duplicate jobs for the same source generation; and
7. expose queued/running work visibly to the user.

There is no background daemon in this tranche.

## One-time imports remain first-class

Remembered locations do not replace explicit paths.

A desktop UI should continue to support:

```text
Choose files…
Choose folder…
```

without forcing persistent registration. A user can therefore process ten recordings from Downloads and never grant EchoFlow ongoing discovery permission for Downloads.

Similarly, `library refresh PATH...` remains a valid one-time/external canonical discovery operation. Once an individual external canonical transcript enters the lexical index, its tracked canonical path remains part of refresh reconciliation while it exists, independent of whether its containing directory was remembered.

## Desktop presentation contract

The GUI should present the backend concepts in user language, for example:

```text
Use this folder

(•) Just this time
( ) Remember this folder

If remembered as a recording source:
[ ] Automatically process new recordings
```

The automatic checkbox must default off. Transcript-library locations never have a processing policy other than `manual` because transcript discovery never runs ASR.

Temporarily unavailable roots should appear as unavailable/offline, not as deleted configuration. Removing a remembered location must only forget the permission record; it must never delete the directory or its contents.

## Why this exists before the GUI

The desktop client should consume one stable backend contract rather than inventing persistence rules in TypeScript. By landing location identity, persistence, discovery, and policy boundaries first, Tauri/React can remain a thin adapter over application-owned behavior.
