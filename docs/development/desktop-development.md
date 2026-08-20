# Desktop development prerequisites 🖥️

EchoFlow's packaged desktop application is intended for **normal users who install and run
an application**. Rust, Node.js, npm, Cargo, Vite, and the Tauri CLI are developer/build
tools. They are not intended to become end-user prerequisites.

Until signed installers exist, contributors running the native desktop shell from source
need the toolchains below.

## What installs where

`npm ci` is project-local by default. From `frontend/`, it installs the exact dependency
graph from `package-lock.json` into `frontend/node_modules/`.

That is not a global machine install. It is closer to a repository-local dependency tree
than to Python's activated virtual environment model. Global npm installation requires an
explicit global flag such as `npm install -g ...`; EchoFlow's normal development workflow
does not require that.

Python dependencies remain isolated through EchoFlow's `uv` environment. Rust dependencies
are resolved by Cargo for the Tauri host and cached in Cargo's normal user cache; the build
artifacts for this application live under `frontend/src-tauri/target/` unless Cargo is
configured otherwise.

## Required developer toolchains

Before running the native desktop shell, verify:

```bash
node --version
npm --version
cargo --version
rustc --version
```

The repository's `frontend/package.json` declares the supported Node runtime range. Use a
stable Rust toolchain.

On Arch/Manjaro, one reasonable Rust setup is:

```bash
sudo pacman -S rustup
rustup default stable
```

Tauri also needs native webview/build libraries supplied by the operating system. Package
names differ by distribution. On Arch/Manjaro the common development prerequisites include
GTK/WebKitGTK and normal build tooling; use the current Tauri Linux prerequisite guidance
for your distribution rather than copying package names from another OS blindly.

## Install the locked frontend graph

```bash
cd frontend
npm ci
```

`npm ci` is preferred over a casual `npm install` for a clean checkout because it treats
`package-lock.json` as authoritative and reproduces the locked dependency graph.

For browser-only React development and Playwright's mock desktop authority:

```bash
npm run dev
```

For the real Tauri host:

```bash
npm run tauri dev
```

The Tauri path compiles Rust and therefore exercises native application configuration that
a Vite-only build cannot prove.

## Native host smoke

CI runs a native Tauri host compile check in addition to TypeScript/Vite checks. This is
intentional: frontend compilation alone will not catch missing Rust assets, invalid Tauri
configuration, or native host compile errors.

The checked-in `frontend/src-tauri/icons/icon.png` is required by Tauri's generated context.
Do not delete or rename native assets merely because the browser frontend does not import
them.

## Clean-up

Project-local JavaScript dependencies may be removed at any time and restored from the
lockfile:

```bash
rm -rf frontend/node_modules
cd frontend
npm ci
```

Rust build outputs are also disposable:

```bash
cargo clean --manifest-path frontend/src-tauri/Cargo.toml
```

Neither operation deletes EchoFlow recordings, canonical transcripts, or durable research
state. Those are product data, not build artifacts.
