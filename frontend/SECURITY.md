# EchoFlow desktop frontend security

The desktop client is a presentation and native-host boundary over EchoFlow's local Python application. It is not a second source of business authority.

## Trust boundary

The React/WebView layer may display sensitive transcript text, research notes, tags, collection names, speaker labels, paths the user has explicitly selected, and bounded source-declared audio-track labels returned by preflight. Those values are data. They must never become trusted markup or executable content.

The frontend does not receive arbitrary SQL, shell, database, model-provider, media-probe, or filesystem capabilities. Tauri exposes narrow commands for specific human workflows. Python validates versioned, size-bounded requests with closed schemas before application services run.

The ordinary desktop bridge is fixed to `python -m echoflow.desktop.bridge`. Transcript inspection and speaker management use the separate fixed `python -m echoflow.desktop.transcript_tools_bridge` entry point through Tauri's `transcript_tools_request` command. The webview cannot choose either Python module, substitute a shell command, or provide an arbitrary backend method. The transcript-tools bridge currently allowlists only inspect, speaker presentation, speaker-label set/remove, and deterministic publication operations.

Verified playback has a stricter split. The Python `echoflow.desktop.playback_bridge` is **not** exposed as a Tauri command. Only Rust's fixed `playback_prepare` implementation may call it. That private bridge returns the verified source path to Rust so Rust can open the file, but the raw grant never crosses into the webview.

Adding a desktop capability requires all three layers to agree deliberately:

1. a typed frontend request/response contract;
2. an explicit Tauri/native capability when native privilege is required; and
3. a validated Python bridge method that delegates to an application service.

React must not recreate application policy by opening DuckDB, SQLite, canonical JSON, arbitrary local files, FFprobe, or subprocesses directly.

## Explicit embedded-audio-track selection

A source file may contain several audio streams. The low-level planner has a deterministic primary stream so probing/planning remains reproducible, but Processing Center must not silently reinterpret that default as user intent.

Python owns the decision. A preflight with multiple audio streams and no requested stream returns `audio_stream_selection_required=true`. The frontend then:

- presents the bounded stream facts returned by Python;
- keeps **Start local transcription** disabled;
- accepts a human radio-button choice;
- sends only the selected integer stream index back to the existing typed preflight operation; and
- enables Start only after Python returns a new plan bound to that stream.

React does not infer the best microphone, prefer the container default, inspect audio quality, or validate whether an index exists. Those would be duplicated media/business policy.

For multi-track files, Python may expose bounded source-declared `title`, `language`, and `is_default` display fields plus codec/sample-rate/channel facts. Title and language are length-bounded before crossing the desktop DTO. They remain untrusted text and are not source identity. No source path is added to the multi-track response.

A new recording selection clears any previously selected stream in the presentation state so a choice from one source cannot leak into another source's initial preflight. Fresh retry likewise begins without inheriting an unrelated presentation choice; checkpoint resume restores the stream from its backend checkpoint contract.

## Generation-bound transcript mutations and playback

A long-lived desktop view can become stale while the library changes. Speaker numbering is meaningful only inside the canonical transcript generation that produced it. Every transcript-tools inspect, speaker presentation, label mutation, and publication request therefore carries `(document_id, canonical_sha256)`.

Playback carries the same exact generation identity plus a finite non-negative source-relative coordinate. Python verifies canonical bytes, source identity, current source SHA-256/size, duration bounds, and audio-stream identity before playback can be granted. A stale desktop view or changed source is rejected rather than reconciled in React.

Multi-audio **playback** currently fails closed. Canonical evidence records which audio stream was transcribed, but the system WebView cannot portably guarantee that it will render that exact track from every multi-track container. EchoFlow therefore refuses ambiguous playback instead of presenting one track as evidence for another.

This does not conflict with multi-track transcription. Transcription owns explicit FFmpeg extraction and can prove which selected stream entered ASR; current WebView playback cannot yet prove its rendered embedded track.

## Opaque native media capability

Rust immediately opens the source authorized by Python and rechecks its size and modification timestamp to narrow the verification/open race. The opened `File` is stored behind an opaque active-session token.

The `echoflow-media` protocol accepts only active closed-format session IDs. It does not accept paths. Its transport boundary is deliberately narrow:

- `GET` and `HEAD` only;
- no arbitrary path lookup or filesystem scope;
- malformed, random, expired, or path-like tokens return no media;
- multipart ranges are rejected;
- each response body is capped at 1 MiB;
- at most eight playback sessions may be active;
- media responses use `Cache-Control: no-store`; and
- `playback_release` revokes the session.

Session IDs are opaque handles, not independent evidence authority. Creating a session still requires Python's generation/source authorization.

## Rendering untrusted local content

React's normal text rendering is the default boundary for transcript, research, filename, speaker, and audio-track metadata. `dangerouslySetInnerHTML` is prohibited unless a future security review adds an explicit sanitizer and a narrowly documented use case. CI rejects its use today.

Search snippets, note bodies, participant-provided text, filenames, speaker labels, source-declared track titles/languages, and metadata remain text. A malicious recording filename, track title, or transcript containing HTML/script syntax must remain inert in the WebView.

The packaged frontend uses no remote fonts, scripts, stylesheets, analytics, or application telemetry. Network-bearing product behavior must be explicit and separately designed rather than smuggled through presentation code.

## In-app guidance is presentation only

`frontend/src/help.ts` contains static local explanatory copy. `InfoPopover` renders that copy through ordinary React text nodes. The guidance layer has no filesystem, database, subprocess, model, media, or network capability and does not load remote documentation.

Help may explain an application rule, such as generation binding, deliberate multi-audio playback refusal, or the need to choose among embedded tracks, but it does not evaluate or enforce those rules. Python remains authoritative. Treating help copy as executable policy would create exactly the duplicate frontend business logic this boundary is designed to avoid.

Guidance must not interpolate source/canonical paths, transcript contents, research contents, or other sensitive state into reusable help text. The multi-track chooser is a special inline case: it renders only bounded stream display facts already returned by backend preflight. Tests assert path non-disclosure while help is open.

## Path and evidence disclosure

Local paths are sensitive. Intake may intentionally show paths the user has just selected because reviewing that selection is part of the requested action. Evidence navigation, transcript tooling, playback, and multi-track metadata presentation are narrower.

Search/discovery responses return evidence identity, verified segment/word coordinates, seek time, speaker display state, and research metadata without canonical/source filesystem paths. Transcript-tools responses return generation identity, source availability/provenance, speaker state, and publication **filenames**, not canonical/source paths or the selected publication directory. The native folder dialog returns a destination only to the local client so it can submit that explicit intent to Python.

Processing preflight may already operate on a path the user selected, but its returned multi-track DTO exposes only stream index plus bounded descriptive media facts. It does not add another filesystem disclosure surface.

Playback responses to React contain only an opaque session/token, media kind, verified duration, and safe seek coordinate. The source path exists only inside the private Python-to-Rust authorization hop and the Rust session. React never receives it and cannot choose an arbitrary playback file.

The frontend must not copy path-bearing values into routine logs. EchoFlow currently has no application telemetry.

## Derived publication

TXT, SRT, and WebVTT are derived views, not transcript authority. React chooses requested formats and a user-selected destination. Python verifies the expected canonical generation, renders the formats, applies collision-safe filename allocation, writes the files, and returns safe filenames. Presentation code must not implement subtitle timing, speaker cue rules, or collision policy.

## Content Security Policy and Tauri capabilities

Production and development Content Security Policies are separate. Production does not permit the Vite development WebSocket endpoint. Development may allow the local HMR WebSocket required by Vite. Script execution remains restricted to the application origin.

Media is restricted to the application origin and EchoFlow's dedicated `echoflow-media` protocol, including the localhost representation Tauri uses on platforms that require it. EchoFlow does not add general `file:`, `blob:`, or arbitrary localhost media access.

The main window capability grants Tauri's core defaults plus the native open dialog and explicit EchoFlow commands. New permissions should be added one at a time with a concrete user workflow and security rationale. Broad shell, filesystem, process, or database permissions are not acceptable substitutes for a typed application method.

## Frontend dependency supply chain

Build and test dependencies are security-relevant even when they are not shipped as runtime JavaScript. Vite, Playwright, Tauri tooling, and compiler/bundler dependencies execute during development or CI and influence generated assets.

`frontend/package-lock.json` is therefore part of the security boundary. CI installs with `npm ci` and fails on high-severity advisories across the complete locked graph. Dependency updates that change native bindings or browser automation versions must pass TypeScript, production build, native Cargo, Playwright, accessibility, and platform-smoke checks.

Do not hand-edit lockfile integrity hashes.

## What current tests prove

Python tests cover allowlists, schema validation, stale-generation rejection, error masking, speaker authority, deterministic publication, playback generation/source verification, stream ambiguity, media-probe bounds, embedded-track display metadata, and explicit multi-track confirmation policy. Hypothesis exercises generation-bound and bounded-seek invariants. Targeted Poodle mutation workflows challenge decision-heavy backend code without making every pull request pay the full mutation cost.

Rust tests cover playback session-token validation, range parsing, unknown sessions, and bounded protocol responses. CI runs both `cargo check --locked` and `cargo test --locked` for the native host.

Frontend tests cover each primary workspace, transcript-tool interactions, verified playback, multi-track Processing preflight, contextual help, hostile-text rendering, keyboard paths, path/capability boundaries, theme persistence/contrast, and axe. Playback qualification includes current and preserved older generations, exact word coordinates, missing/changed/multi-audio failures, audio/video presentation, keyboard preparation, and path non-disclosure. Multi-track Processing qualification proves that no stream is pre-confirmed, Start is blocked until explicit choice, a chosen index is rebound through preflight, and axe remains clean. Guidance qualification includes keyboard dismissal/focus return, screen-sensitive topics, contextual evidence/playback/transcript help, axe with an open panel, and path non-disclosure. Pride and Monochrome use the same semantic-token qualification as every other skin.

These checks do not prove that the host OS, system WebView, Tauri runtime, registry infrastructure, native dependencies, or a compromised same-user process are trustworthy. Native codec availability also varies by operating-system media engine. Packaging, signing, update integrity, managed Python runtime custody, and representative-device WebView qualification remain separate release milestones.
