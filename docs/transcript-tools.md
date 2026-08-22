# Transcript and speaker tools

Scholion's desktop transcript tools make a produced canonical transcript easier to inspect, name, read, and publish without turning React into a second transcript authority.

## Authority boundary

A transcript-tools view is opened with exactly:

```text
document_id
canonical_sha256
```

Python re-resolves that identity against the current library and verifies canonical bytes before returning transcript details or accepting a mutation. React never parses canonical JSON and never decides whether a displayed generation is still current.

This matters because speaker refs such as `speaker-02` are recording/generation-scoped evidence. A newer transcription may reuse the same friendly ref for a different voice cluster. Every inspect, speaker transcript, speaker-label mutation, and publication request therefore carries the canonical digest that the user actually opened. If the generation changed, Scholion refuses the operation and requires the view to be reopened.

## What the desktop can do

From a Library transcript result, **Transcript tools** provides:

- transcript duration, language, segment/speaker counts, source availability, and generation identity;
- selected audio-stream detail and processing provenance under **Technical details**;
- human display-name editing while anonymous speaker refs remain visible;
- a derived speaker transcript that preserves handoffs, overlap, mixed-unresolved, and unattributed states; and
- post-hoc TXT, SRT, and WebVTT publication to a user-selected folder.

These features reuse existing Python authorities. They do not rewrite canonical transcript evidence.

## Speaker names remain human knowledge

Diarization says that some interval belongs to an anonymous ref such as `speaker-02`. A user may separately say that they know this person as `Dr. Chen`.

The desktop can then show:

```text
Dr. Chen · speaker-02
```

The anonymous ref remains visible and remains the evidence identity. Removing a name removes only the human-authored label. It does not alter diarization evidence or search coordinates.

For the underlying storage and generation semantics, see [Speaker display names](speaker-names.md).

## Speaker-aware reading is derived presentation

The speaker transcript combines verified canonical word timing, the stored diarization turn timeline, and current-generation display labels. The backend returns explicit span kinds:

- `single-speaker`;
- `overlap`;
- `mixed-unresolved`; and
- `unattributed`.

React maps those to ordinary labels such as **Speaker**, **Overlap**, **Mixed speakers**, and **Unattributed**. It does not choose a winner when two speakers overlap, promote uncertain text to a single speaker, or derive new speaker assignments.

## Post-hoc publication

TXT, SRT, and WebVTT are deterministic derived views. The flow is deliberately narrow:

1. Tauri opens a native folder picker;
2. React submits the selected destination, requested formats, document ID, and expected canonical digest;
3. Python verifies the generation;
4. Python renders the formats and allocates collision-safe filenames; and
5. the desktop receives publication filenames, not source/canonical paths.

Presentation code does not implement subtitle timing, speaker cue rules, or filename collision policy.

## Desktop security boundary

Tauri exposes a dedicated `transcript_tools_request` command that invokes the fixed Python module `scholion.desktop.transcript_tools_bridge`. The webview cannot supply a Python module or arbitrary command.

The bridge has a closed method allowlist for inspect, speaker presentation, speaker-label set/remove, and publication. Requests are versioned and size bounded. Method parameters are validated through closed Pydantic schemas before an application service is called.

The transcript-tools DTO intentionally omits canonical/source paths and the selected publication directory from responses.

## Testing

Backend qualification includes positive, negative, and boundary tests for generation binding, tampered canonical bytes, missing source recordings, speaker mutation, export collisions, and invalid method/format requests. Hypothesis exercises invalid generation-digest inputs. A targeted manual Poodle workflow mutates the decision-heavy transcript-tool services.

Frontend Playwright coverage verifies transcript details, path non-disclosure, speaker rename/remove behavior, explicit overlap presentation, format selection/publication, the zero-format boundary, and axe accessibility. The theme matrix independently qualifies the panel's shared semantic colors through the global token contract.

Mutation testing remains concentrated in Python because canonical-generation, custody, speaker, and export decisions belong there. Stryker is not currently installed merely to mutate presentation JSX. If meaningful decision-heavy pure frontend modules emerge later, a JavaScript mutation layer can be added where it tests real policy rather than compensating for misplaced business logic.

## Performance

Transcript inspection intentionally verifies canonical bytes before trusting them. That is linear I/O in one canonical JSON file and is bounded by Scholion's canonical-read limit. The speaker transcript is loaded lazily so opening transcript details does not pay for a second presentation pass unless requested.

Do not optimize this by caching unverified/stale canonical content in React. If profiling later shows canonical verification becoming a real interactive bottleneck at large corpus/file sizes, optimize behind a generation-keyed backend reader/cache with explicit invalidation.
