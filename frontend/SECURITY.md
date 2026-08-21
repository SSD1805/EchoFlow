# EchoFlow desktop frontend security

The desktop client is a presentation and native-host boundary over EchoFlow's local Python application. It is not a second source of business authority.

## Trust boundary

The React/WebView layer may display sensitive transcript text, research notes, tags, collection names, speaker labels, and paths the user has explicitly selected. Those values are data. They must never become trusted markup or executable content.

The frontend does not receive arbitrary SQL, shell, database, model-provider, or filesystem capabilities. Tauri exposes narrow commands for specific human workflows. Python validates versioned, size-bounded requests with closed schemas before application services run.

The ordinary desktop bridge is fixed to `python -m echoflow.desktop.bridge`. Transcript inspection and speaker management use the separate fixed `python -m echoflow.desktop.transcript_tools_bridge` entry point through Tauri's `transcript_tools_request` command. The webview cannot choose either Python module, substitute a shell command, or provide an arbitrary backend method. The transcript-tools bridge currently allowlists only inspect, speaker presentation, speaker-label set/remove, and deterministic publication operations.

Verified playback has a stricter split. The Python `echoflow.desktop.playback_bridge` is **not** exposed as a Tauri command. Only Rust's fixed `playback_prepare` implementation may call it. That private bridge returns the verified source path to Rust so Rust can open the file, but the raw grant never crosses into the webview.

Adding a desktop capability requires all three layers to agree deliberately:

1. a typed frontend request/response contract;
2. an explicit Tauri/native capability when native privilege is required; and
3. a validated Python bridge method that delegates to an application service.

React must not recreate application policy by opening DuckDB, SQLite, canonical JSON, arbitrary local files, or subprocesses directly.

## Generation-bound transcript mutations and playback

A long-lived desktop view can become stale while the library changes. Speaker numbering is meaningful only inside the canonical transcript generation that produced it. Every transcript-tools inspect, speaker presentation, label mutation, and publication request therefore carries `(document_id, canonical_sha256)`.

Playback carries the same exact generation identity plus a finite non-negative source-relative coordinate. Python verifies canonical bytes, source identity, current source SHA-256/size, duration bounds, and audio-stream identity before playback can be granted. A stale desktop view or changed source is rejected rather than reconciled in React.

Multi-audio sources currently fail closed. Canonical evidence records which audio stream was transcribed, but the system WebView cannot portably guarantee that it will render that exact track from every multi-track container. EchoFlow therefore refuses ambiguous playback instead of presenting one track as evidence for another.

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

React's normal text rendering is the default boundary for transcript and research content. `dangerouslySetInnerHTML` is prohibited unless a future security review adds an explicit sanitizer and a narrowly documented use case. CI rejects its use today.

Search snippets, note bodies, participant-provided text, filenames, speaker labels, and metadata remain text. A malicious recording filename or transcript containing HTML/script syntax must remain inert in the WebView.

The packaged frontend uses no remote fonts, scripts, stylesheets, analytics, or application telemetry. Network-bearing product behavior must be explicit and separately designed rather than smuggled through presentation code.

## In-app guidance is presentation only

`frontend/src/help.ts` contains static local explanatory copy. `InfoPopover` renders that copy through ordinary React text nodes. The guidance layer has no filesystem, database, subprocess, model, media, or network capability and does not load remote documentation.

Help may explain an application rule, such as generation binding or deliberate multi-audio playback refusal, but it does not evaluate or enforce that rule. Python remains authoritative. Treating help copy as executable policy would create exactly the duplicate frontend business logic this boundary is designed to avoid.

Guidance must not interpolate source/canonical paths, transcript contents, research contents, or other sensitive state into reusable help text. Tests assert path non-disclosure while help is open.

## Path and evidence disclosure

Local paths are sensitive. Intake may intentionally show paths the user has just selected because reviewing that selection is part of the requested action. Evidence navigation, transcript tooling, and playback are narrower.

Search/discovery responses return evidence identity, verified segment/word coordinates, seek time, speaker display state, and research metadata without canonical/source filesystem paths. Transcript-tools responses return generation identity, source availability/provenance, speaker state, and publication **filenames**, not canonical/source paths or the selected publication directory. The native folder dialog returns a destination only to the local client so it can submit that explicit intent to Python.

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

Python tests cover allowlists, schema validation, stale-generation rejection, error masking, speaker authority, deterministic publication, playback generation/source verification, stream ambiguity, and other application semantics. Hypothesis exercises generation-bound and bounded-seek invariants. Targeted Poodle mutation workflows challenge decision-heavy backend code without making every pull request pay the full mutation cost.

Rust tests cover playback session-token validation, range parsing, unknown sessions, and bounded protocol responses. CI runs both `cargo check --locked` and `cargo test --locked` for the native host.

Frontend tests cover each primary workspace, transcript-tool interactions, verified playback, contextual help, hostile-text rendering, keyboard paths, path/capability boundaries, theme persistence/contrast, and axe. Playback qualification includes current and preserved older generations, exact word coordinates, missing/changed/multi-audio failures, audio/video presentation, keyboard preparation, and path non-disclosure. Guidance qualification includes keyboard dismissal/focus return, screen-sensitive topics, contextual evidence/playback/transcript help, axe with an open panel, and path non-disclosure. Pride and Monochrome use the same semantic-token qualification as every other skin.

These checks do not prove that the host OS, system WebView, Tauri runtime, registry infrastructure, native dependencies, or a compromised same-user process are trustworthy. Native codec availability also varies by operating-system media engine. Packaging, signing, update integrity, managed Python runtime custody, and representative-device WebView qualification remain separate release milestones.
