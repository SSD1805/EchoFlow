# EchoFlow desktop frontend security

The desktop client is a presentation and native-host boundary over EchoFlow's local Python application. It is not a second source of business authority.

## Trust boundary

The React/WebView layer may display sensitive transcript text, research notes, tags, collection names, speaker labels, and paths the user has explicitly selected. Those values are data. They must never become trusted markup or executable content.

The frontend does not receive arbitrary SQL, shell, database, model-provider, or filesystem capabilities. Tauri exposes narrow commands for specific human workflows. Python validates versioned, size-bounded requests with closed schemas before application services run.

The ordinary desktop bridge is fixed to `python -m echoflow.desktop.bridge`. Transcript inspection and speaker management use the separate fixed `python -m echoflow.desktop.transcript_tools_bridge` entry point through Tauri's `transcript_tools_request` command. The webview cannot choose either Python module, substitute a shell command, or provide an arbitrary backend method. The transcript-tools bridge currently allowlists only inspect, speaker presentation, speaker-label set/remove, and deterministic publication operations.

Adding a desktop capability requires all three layers to agree deliberately:

1. a typed frontend request/response contract;
2. an explicit Tauri/native capability when native privilege is required; and
3. a validated Python bridge method that delegates to an application service.

React must not recreate application policy by opening DuckDB, SQLite, canonical JSON, arbitrary local files, or subprocesses directly.

## Generation-bound transcript mutations

A long-lived desktop view can become stale while the library changes. Speaker numbering is meaningful only inside the canonical transcript generation that produced it. Every transcript-tools inspect, speaker presentation, label mutation, and publication request therefore carries `(document_id, canonical_sha256)`.

Python verifies that generation at the service boundary. A stale desktop view is rejected rather than silently applying a human label or publication request to a newer generation that happens to reuse `speaker-02` or a segment identifier. React may present the rejection and ask the user to reopen the transcript; it may not reconcile generations itself.

## Rendering untrusted local content

React's normal text rendering is the default boundary for transcript and research content. `dangerouslySetInnerHTML` is prohibited unless a future security review adds an explicit sanitizer and a narrowly documented use case. CI rejects its use today.

Search snippets, note bodies, participant-provided text, filenames, speaker labels, and metadata remain text. A malicious recording filename or transcript containing HTML/script syntax must remain inert in the WebView.

The packaged frontend uses no remote fonts, scripts, stylesheets, analytics, or application telemetry. Network-bearing product behavior must be explicit and separately designed rather than smuggled through presentation code.

## Path and evidence disclosure

Local paths are sensitive. Intake may intentionally show paths the user has just selected because reviewing that selection is part of the requested action. Evidence navigation and transcript tooling are narrower.

Search/discovery responses return evidence identity, verified segment/word coordinates, seek time, speaker display state, and research metadata without canonical/source filesystem paths. Transcript-tools responses return generation identity, source availability/provenance, speaker state, and publication **filenames**, not canonical/source paths or the selected publication directory. The native folder dialog returns a destination only to the local client so it can submit that explicit intent to Python.

The frontend must not copy path-bearing values into routine logs. EchoFlow currently has no application telemetry.

## Derived publication

TXT, SRT, and WebVTT are derived views, not transcript authority. React chooses requested formats and a user-selected destination. Python verifies the expected canonical generation, renders the formats, applies collision-safe filename allocation, writes the files, and returns safe filenames. Presentation code must not implement subtitle timing, speaker cue rules, or collision policy.

## Content Security Policy and Tauri capabilities

Production and development Content Security Policies are separate. Production does not permit the Vite development WebSocket endpoint. Development may allow the local HMR WebSocket required by Vite. Script execution remains restricted to the application origin.

The main window capability grants Tauri's core defaults plus the native open dialog and explicit EchoFlow commands. New permissions should be added one at a time with a concrete user workflow and security rationale. Broad shell, filesystem, process, or database permissions are not acceptable substitutes for a typed application method.

## Frontend dependency supply chain

Build and test dependencies are security-relevant even when they are not shipped as runtime JavaScript. Vite, Playwright, Tauri tooling, and compiler/bundler dependencies execute during development or CI and influence generated assets.

`frontend/package-lock.json` is therefore part of the security boundary. CI installs with `npm ci` and fails on high-severity advisories across the complete locked graph. Dependency updates that change native bindings or browser automation versions must pass TypeScript, production build, native Cargo, Playwright, accessibility, and platform-smoke checks.

Do not hand-edit lockfile integrity hashes.

## What current tests prove

Python tests cover allowlists, schema validation, stale-generation rejection, error masking, speaker authority, deterministic publication, collision behavior, and other application semantics. Hypothesis exercises generation-bound input invariants. Targeted Poodle mutation workflows challenge decision-heavy backend code without making every pull request pay the full mutation cost.

Frontend tests cover each primary workspace, transcript-tool interactions, hostile-text rendering, keyboard paths, path/capability boundaries, theme persistence/contrast, and axe. Pride and Monochrome use the same semantic-token qualification as every other skin.

These checks do not prove that the host OS, system WebView, Tauri runtime, registry infrastructure, native dependencies, or a compromised same-user process are trustworthy. Packaging, signing, update integrity, managed Python runtime custody, and representative-device WebView qualification remain separate release milestones.
