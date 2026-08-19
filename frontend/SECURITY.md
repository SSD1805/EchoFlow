# EchoFlow desktop frontend security

The desktop client is a presentation and native-host boundary over EchoFlow's local Python application. It is not a second source of business authority.

## Trust boundary

The React/WebView layer may display sensitive transcript text, research notes, tags, collection names, speaker labels, and user-selected local paths. Those values are data. They must never be treated as trusted markup or executable content.

The desktop frontend does not receive arbitrary SQL, shell, database, or filesystem capabilities. Tauri exposes only the permissions required by the current human workflow, and the Rust host forwards a versioned, size-bounded request to the fixed `python -m echoflow.desktop.bridge` entry point. Python validates the method and method-specific parameters with closed schemas before application services run.

Adding a new desktop capability therefore requires all three layers to agree deliberately:

1. a typed frontend request/response contract;
2. an explicit Tauri/native capability when native privilege is required; and
3. a validated Python bridge method that delegates to an existing application service.

The frontend must not bypass those services by opening DuckDB, SQLite, arbitrary local files, or subprocesses directly.

## Rendering untrusted local content

React's normal text rendering is the default boundary for transcript and research content. `dangerouslySetInnerHTML` is prohibited in the EchoFlow frontend unless a future security review introduces an explicit sanitizer and a narrowly documented use case. CI rejects its use today.

Search snippets, note bodies, participant-provided text, filenames, and metadata must be rendered as text. A malicious recording filename or transcript containing HTML or script syntax must remain inert text in the WebView.

The packaged frontend uses no remote fonts, scripts, stylesheets, or analytics. Network-bearing product behavior must be explicit and separately designed rather than smuggled through presentation code.

## Path and evidence disclosure

Local paths are sensitive. Intake may intentionally show paths the user just selected because that is part of the command result they requested. Search/discovery responses are narrower: the desktop bridge returns evidence identity, verified segment/word coordinates, seek time, speaker display state, and research metadata without returning canonical or source filesystem paths.

The frontend must not copy path-bearing values into telemetry or routine logs. EchoFlow currently has no application telemetry.

## Content Security Policy and Tauri capabilities

Production and development Content Security Policies are separate. Production does not permit the Vite development WebSocket endpoint. Development may allow the local HMR WebSocket required by Vite. Script execution remains restricted to the application origin.

The main window capability currently grants Tauri's core defaults plus the native open dialog. New permissions should be added one at a time with a concrete user workflow and security rationale. Broad shell, filesystem, process, or database permissions are not acceptable substitutes for a typed application method.

## Frontend dependency supply chain

Build and test dependencies are security-relevant even when they are not shipped as runtime JavaScript. Vite, its compiler/bundler graph, Playwright, and other development packages execute code during development or CI and can influence generated application assets.

`frontend/package-lock.json` is therefore part of the security boundary. CI installs with `npm ci` and fails on high-severity advisories across the complete locked dependency graph, not only production dependencies. Dependency updates that change native build bindings or browser automation versions must still pass TypeScript, the production build, Playwright, and accessibility tests.

Do not hand-edit lockfile integrity hashes. Regenerate the lockfile with npm from the pinned manifest and review the resulting dependency graph.

## What current tests prove

Playwright plus axe verifies browser-level interaction and automated accessibility behavior for covered workflows. Python tests verify the bridge allowlist, schema validation, error masking, and application semantics. These checks do not prove that the host OS, system WebView, Tauri runtime, Node/npm registry, native dependencies, or a compromised same-user process are trustworthy.

Packaging, code signing, update integrity, managed Python runtime custody, and representative-device WebView qualification remain separate release milestones.
