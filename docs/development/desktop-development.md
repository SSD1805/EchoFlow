# Desktop development prerequisites 🖥️

Scholion's packaged desktop application is intended for **normal users who install and run
an application**. Rust, Node.js, npm, Cargo, Vite, WebKitGTK, and the Tauri CLI are
source-build tools. They are not intended to become end-user prerequisites.

Until signed installers exist, contributors can choose the smallest development mode that
matches what they are trying to do.

## Choose a mode first

| I want to… | Start with | Required layers |
|---|---|---|
| inspect or work on the React UI with fake data | `npm run dev:mock` | Node + npm |
| run the real native Scholion window | `npm run tauri dev` | Node/npm + Rust/Cargo + OS-native Tauri libraries; Python for backend actions |
| transcribe real media from source | native app or CLI processing flow | Python/uv + FFmpeg + managed transcription model, in addition to the relevant UI/native layers |

A transcription model is not required to start the browser mock or render the native
window. Rust is not required for browser-only UI work.

If you are unsure what your machine has, from `frontend/` run:

```bash
npm run doctor:desktop
```

For browser-only work:

```bash
npm run doctor:desktop -- --mode=mock
```

The detailed symptom-by-symptom recovery guide is **[Desktop source-build troubleshooting](troubleshooting.md)**.

## What installs where

`npm ci` is project-local by default. From `frontend/`, it installs the exact dependency
graph from `package-lock.json` into:

```text
frontend/node_modules/
```

That is not a global machine install. Global npm installation requires an explicit flag such
as `npm install -g ...`; Scholion's development workflow does not require it.

`uv sync` creates/updates Scholion's repository-local Python environment:

```text
.venv/
```

Cargo downloads Rust packages into Cargo's normal user cache. Scholion's disposable native
build output lives under:

```text
frontend/src-tauri/target/
```

The application repository commits `frontend/src-tauri/Cargo.lock` so Rust dependency
resolution is reproducible even though Cargo's package cache itself is shared.

## Browser-only React development

This is the smallest path and is the right choice if you only want to inspect the current
frontend or work on presentation/interactions.

```bash
cd frontend
npm ci
npm run doctor:desktop -- --mode=mock
npm run dev:mock
```

`dev:mock` opens the Vite app with explicit `?e2e=1` fake local data. Mock mode is opt-in so
an ordinary browser can never silently impersonate the real Tauri/Python authority.

If you run plain:

```bash
npm run dev
```

in an ordinary browser, Scholion shows a development-mode notice instead of the real
workspace. Plain `dev` remains the Vite server used internally by `tauri dev`.

## Native Tauri source development

Before the first native build, verify:

```bash
node --version
npm --version
cargo --version
rustc --version
```

The repository's `frontend/package.json` declares the supported Node runtime range. Use a
stable Rust toolchain.

On Arch/Manjaro, one Rust setup is:

```bash
sudo pacman -S rustup
rustup default stable
```

Tauri also needs the operating system's native webview/build libraries. On Arch/Manjaro, a
typical Tauri 2 development set is:

```bash
sudo pacman -S --needed \
  base-devel \
  webkit2gtk-4.1 \
  curl \
  wget \
  file \
  openssl \
  appmenu-gtk-module \
  libappindicator-gtk3 \
  librsvg
```

Package names can evolve with distributions. The desktop doctor checks that the critical
WebKitGTK/GTK development interfaces are actually discoverable rather than assuming a
package command succeeded.

Install the locked JavaScript graph:

```bash
cd frontend
npm ci
```

Then run the native readiness check:

```bash
npm run doctor:desktop
```

### Python backend for real application actions

The Rust host delegates application/evidence rules to the local Python bridge. In a source
checkout it automatically prefers the repository's `.venv` when present.

From the repository root:

```bash
uv sync --locked --extra transcription
```

You normally do **not** need to activate that virtual environment and you do not need to set
`SCHOLION_PYTHON`; the debug Tauri host discovers it. Advanced users can explicitly override
the interpreter with `SCHOLION_PYTHON=/path/to/python`.

Now launch:

```bash
cd frontend
npm run tauri dev
```

Model installation is a later processing prerequisite. Do it when you actually want to
transcribe, not merely to prove the window opens.

## Dependency locking and the Tauri version family

Scholion has JavaScript Tauri packages and Rust Tauri crates. They must evolve as one tested
family.

The intended versions live in:

```text
frontend/tauri-versions.json
```

Validate them with:

```bash
npm run check:tauri-versions
```

`package-lock.json` freezes the JavaScript graph. `src-tauri/Cargo.lock` freezes the Rust
graph. Native CI runs Cargo with `--locked`, so an accidental dependency-resolution change
fails rather than quietly producing a different desktop runtime.

Do not troubleshoot a mismatch by globally installing a different Tauri CLI. Scholion uses
the repository-local npm CLI.

## Port 5173 is deliberately strict

Tauri's development URL is fixed to `http://localhost:5173`. Vite normally selects another
port when 5173 is busy, but that would leave Tauri pointing at the wrong server. Scholion
therefore runs Vite with `--strictPort`.

If 5173 is occupied, stop the old development process and rerun. See the troubleshooting
guide for platform-specific inspection commands.

## Native host smoke

CI compiles the native Tauri host in addition to TypeScript/Vite checks. Frontend compilation
alone cannot catch missing native assets, invalid Rust configuration, Tauri version drift,
or native host compile failures.

The checked-in `frontend/src-tauri/icons/icon.png` is required by Tauri's generated context.
Do not delete or rename native assets merely because the browser frontend does not import
them.

## Linux display compatibility

Linux Tauri uses WebKitGTK. Most Wayland systems work normally, but some compositor/GPU/
WebKitGTK combinations can produce a protocol-level display failure such as:

```text
Error 71: Protocol error, dispatching to Wayland display
```

That is a display-stack compatibility issue, not a reason to modify Scholion's evidence or
Python state. The troubleshooting guide explains command-scoped DMABUF and X11/XWayland
fallbacks. Scholion does not force those workarounds globally because they are not correct for
every Linux machine.

## Clean-up

Project-local JavaScript dependencies are disposable:

```bash
rm -rf frontend/node_modules
cd frontend
npm ci
```

Rust build output is disposable too:

```bash
cargo clean --manifest-path frontend/src-tauri/Cargo.toml
```

Do **not** delete `frontend/src-tauri/Cargo.lock` as routine cleanup. It is part of the
reviewed build contract.

Neither cleanup command deletes Scholion recordings, canonical transcripts, or durable
research state. Product data and build artifacts live under different custody rules.
