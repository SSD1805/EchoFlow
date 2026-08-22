# Desktop source-build troubleshooting 🧰

This page is for the moment when a terminal prints something that sounds catastrophic even
though the underlying problem is usually one missing tool, one stale dependency tree, or one
Linux display quirk.

The first rule is to identify **which development mode you are trying to run**. Scholion has
three different layers, and they do not need the same prerequisites.

| Goal | Command | What you need |
|---|---|---|
| Inspect/click the React UI with fake data | `npm run dev:mock` | Node + npm only |
| Run the real native Tauri window | `npm run tauri dev` | Node/npm + Rust/Cargo + native OS libraries; Python for backend actions |
| Actually transcribe from source | native app or CLI processing flow | all of the native/Python prerequisites plus FFmpeg and an installed Scholion model |

A transcription model is **not** required merely to launch the UI. Rust is **not** required
for the browser mock. Python is **not** required for the browser mock.

Before chasing an error manually, from `frontend/` run:

```bash
npm run doctor:desktop
```

For the browser-only mock:

```bash
npm run doctor:desktop -- --mode=mock
```

The doctor reports all relevant checks instead of stopping at the first missing prerequisite.

## Start with a known-good checkout

From the repository root:

```bash
git status
```

If you have local changes, do not blindly delete or reset them. Know what they are first.
For a clean checkout, install the locked frontend graph with:

```bash
cd frontend
npm ci
```

`npm ci` installs packages into **`frontend/node_modules/`**. It does not globally install
React, Tauri, Vite, or the rest of Scholion's JavaScript dependencies. A global npm install
requires an explicit command such as `npm install -g ...`; Scholion does not require that.

The Python equivalent is `uv sync`, which creates/updates the repository-local `.venv`.
Cargo has a user-level package cache, while this app's disposable Rust build output lives
under `frontend/src-tauri/target/`.

---

# Symptom: `npm error Missing script: "dev:mock"`

## What it means

Your checkout does not contain the explicit browser-mock script yet, or you are running npm
from a directory whose `package.json` is not Scholion's `frontend/package.json`.

## Check

```bash
pwd
npm run
```

You should be inside the repository's `frontend/` directory, and the script list should
contain `dev:mock`.

## Fix

Update to a revision that contains the script, then reinstall the locked graph if needed:

```bash
cd /path/to/Scholion
# inspect git status before pulling if you have local work
git pull
cd frontend
npm ci
npm run dev:mock
```

Do not fix a missing script with `npm install -g`. The script belongs to the repository, not
to your machine-wide npm installation.

---

# Symptom: plain `npm run dev` opens a page that is not the Scholion workspace

## What it means

This is intentional. `npm run dev` starts the Vite server that the **real Tauri host** also
uses. An ordinary browser does not have Tauri's native filesystem/dialog/IPC capabilities.
Scholion therefore refuses to silently substitute fake data and pretend it is your real
workspace.

Plain Vite shows a development-mode notice explaining the two valid choices.

## If you only want the UI

```bash
npm run dev:mock
```

That opens the explicit `?e2e=1` mock workspace.

## If you want the real native application

```bash
npm run doctor:desktop
npm run tauri dev
```

---

# Symptom: the browser is blank or black

## Why this can happen

Historically, Scholion let a normal browser instantiate its Tauri client even though the
Tauri runtime was absent. The first native call could then fail before useful UI appeared.
The current source tree prevents that by presenting the development-mode notice instead.

A truly blank page now usually means a JavaScript build/runtime error, a stale dev server,
or that you are viewing an older checkout.

## Check step by step

1. Confirm you are in `frontend/`.
2. Stop old Vite/Tauri processes with `Ctrl+C` in the terminals that launched them.
3. Reinstall only the project-local JavaScript graph:

   ```bash
   rm -rf node_modules
   npm ci
   ```

4. Start the explicit mock:

   ```bash
   npm run dev:mock
   ```

5. If the terminal prints a TypeScript/Vite error, fix that error first. Do not install random
   global packages to make it disappear.

The `node_modules` directory is rebuildable developer state. Removing it does not touch
recordings, canonical transcripts, or research state.

---

# Symptom: `failed to run 'cargo metadata' ... No such file or directory (os error 2)`

## What it usually means

Tauri tried to launch Cargo, but `cargo` was not installed or was not visible on your
`PATH`. The words “No such file or directory” often refer to the **Cargo executable**, not
to Scholion's `Cargo.toml`.

## Check

```bash
cargo --version
rustc --version
which cargo        # Linux/macOS
```

On Windows use:

```powershell
Get-Command cargo
```

## Fix

Install a stable Rust toolchain. On Arch/Manjaro, one option is:

```bash
sudo pacman -S rustup
rustup default stable
```

Then open a new shell if necessary and rerun:

```bash
cargo --version
rustc --version
```

Scholion's Tauri manifest is `frontend/src-tauri/Cargo.toml`. You should not need a global
Tauri CLI because the repository already carries its Tauri CLI through npm.

---

# Symptom: `found version mismatch Tauri packages`

## Why it happens

Tauri has JavaScript packages **and** Rust crates. They are two halves of one desktop
runtime. If npm is using one Tauri minor line while Cargo independently resolves a newer
Rust line, the CLI can refuse to run because those halves were not tested as one family.

Scholion previously used exact npm versions but broad Rust declarations such as
`tauri = "2"`, with no committed Cargo lockfile. That allowed Cargo to resolve newer 2.x
crates while npm stayed fixed.

Current Scholion declares the intended family in:

```text
frontend/tauri-versions.json
```

and checks it with:

```bash
npm run check:tauri-versions
```

The Rust graph is also committed in `frontend/src-tauri/Cargo.lock` and CI builds it with
`--locked`.

## Fix

Do **not** globally upgrade or downgrade Tauri by trial and error.

First:

```bash
cd frontend
npm run check:tauri-versions
```

If it fails, `package.json`, `tauri-versions.json`, and `src-tauri/Cargo.toml` probably came
from different revisions or were locally modified. Inspect:

```bash
git status
```

Restore or reconcile those files deliberately. Then:

```bash
npm ci
cargo check --locked --manifest-path src-tauri/Cargo.toml
```

If `--locked` says the lockfile needs to change, that is useful evidence: dependency metadata
changed without the reviewed lockfile changing. Do not delete `Cargo.lock` to make the error
go away.

---

# Symptom: `failed to open icon ... src-tauri/icons/icon.png`

## What it means

Tauri reads native application assets at compile time. The React frontend does not import
the icon, so a Vite build can be perfectly healthy while the native Rust host fails.

## Check

```bash
ls -l src-tauri/icons/icon.png
```

from `frontend/`.

## Fix

Restore the checked-in binary asset from Git. Do not replace it with an empty file or text
placeholder. CI compiles the native host specifically to protect this class of failure.

---

# Symptom: WebKitGTK / GTK / `pkg-config` errors during a Linux native build

## Why it happens

A Tauri Linux app uses the operating system's native webview stack. npm can install the
JavaScript packages and Cargo can download Rust crates, but neither one installs Linux's
GTK/WebKit development libraries for you.

## Check

```bash
pkg-config --version
pkg-config --exists webkit2gtk-4.1 gtk+-3.0 && echo "WebKitGTK/GTK found"
```

The desktop doctor performs the same high-signal check.

## Arch/Manjaro development prerequisites

A typical Tauri 2 development setup uses:

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

Package names can change across distribution releases. If one name is unavailable, use your
distribution's current Tauri 2 prerequisite package rather than substituting an unrelated
library.

Installing these system packages affects the development machine. It is different from
`npm ci`, which is repository-local.

---

# Symptom: `Scholion's local Python service is unavailable`

## Why it happens

The native Rust host is intentionally thin. For application/evidence rules it starts:

```text
python -m scholion.desktop.bridge
```

In a source checkout, Scholion now prefers the repository's `.venv` automatically. If that
environment has not been created yet, native UI can launch but backend-backed actions cannot
work.

## Fix

From the repository root:

```bash
uv sync --locked --extra transcription
```

Then verify:

```bash
.venv/bin/python -c "import scholion; print('Scholion import OK')"   # Linux/macOS
```

On Windows:

```powershell
.venv\Scripts\python.exe -c "import scholion; print('Scholion import OK')"
```

Then rerun:

```bash
cd frontend
npm run doctor:desktop
npm run tauri dev
```

### Advanced override

If you intentionally want a different compatible Python interpreter:

```bash
SCHOLION_PYTHON=/path/to/python npm run tauri dev
```

`SCHOLION_PYTHON` has priority over automatic `.venv` discovery. Do not set it globally
unless you actually want that override for future shells.

### Do I need to install a Whisper model now?

No. A model is needed when you actually ask Scholion to transcribe. It is not a prerequisite
for rendering the UI, starting the Tauri window, browsing an existing library, or testing
the browser mock.

---

# Symptom: `Error 71: Protocol error, dispatching to Wayland display`

## What it usually means

On Linux the Tauri webview is WebKitGTK. WebKitGTK, the GPU/DMABUF renderer, the Wayland
compositor, and the graphics driver all participate in drawing the window. Some combinations
can terminate at the Wayland protocol layer even when Scholion's React and Rust code are
valid.

This is a **display-stack compatibility failure**, not evidence that your transcript library
or Python environment is corrupt.

## First check

Run:

```bash
npm run doctor:desktop
```

If it reports the Tauri/Rust/WebKit prerequisites as healthy and says Wayland is detected,
try the following **one command at a time**.

## Option 1: disable WebKitGTK's DMABUF renderer for this launch

```bash
WEBKIT_DISABLE_DMABUF_RENDERER=1 npm run tauri dev
```

This changes how WebKitGTK hands rendered buffers to the compositor. Because the variable is
prefixed to one command, it does not permanently change your system configuration.

## Option 2: diagnostic X11/XWayland launch

```bash
GDK_BACKEND=x11 npm run tauri dev
```

This asks GTK to use its X11 backend for that launch. If it works while native Wayland does
not, you have isolated the problem to the Wayland/webview/display path rather than Scholion's
application backend.

## Option 3: combine both compatibility switches

```bash
GDK_BACKEND=x11 WEBKIT_DISABLE_DMABUF_RENDERER=1 npm run tauri dev
```

Use this as diagnosis/fallback, not as Scholion's universal default. Different Linux
machines have different GPU/compositor stacks, and globally forcing a backend that fixes one
machine can make another worse.

---

# Symptom: `Port 5173 is already in use`

## Why it now fails instead of silently choosing another port

Tauri's development configuration points to:

```text
http://localhost:5173
```

Vite normally tries 5174, 5175, and so on when its preferred port is occupied. That behavior
is convenient for a standalone website but dangerous here: Tauri would still be looking at
5173 and could connect to the wrong process.

Scholion therefore starts Vite with `--strictPort` and fails loudly.

## Find the old process

Linux:

```bash
ss -ltnp | grep 5173
```

or:

```bash
lsof -i :5173
```

Stop the Vite/Tauri process you previously launched, normally with `Ctrl+C` in its terminal.
Do not kill unrelated processes merely because they use a port.

Then retry:

```bash
npm run dev:mock
# or
npm run tauri dev
```

---

# Symptom: npm dependencies seem stale or impossible

Use the lockfile as authority:

```bash
cd frontend
rm -rf node_modules
npm ci
npm run check:tauri-versions
```

Do not use `npm update` as a troubleshooting hammer. Updating dependencies is a source change
that should be reviewed and committed deliberately.

---

# Symptom: Rust build state seems stale or impossible

You may remove **build output** without removing the Rust lockfile:

```bash
cargo clean --manifest-path frontend/src-tauri/Cargo.toml
```

Then rebuild from the committed graph:

```bash
cargo check --locked --manifest-path frontend/src-tauri/Cargo.toml
```

`target/` is disposable. `Cargo.lock` is not disposable in this application repository; it
is part of the reproducible build contract.

---

# What is safe to delete while troubleshooting?

These are developer/build artifacts and can be regenerated:

```text
frontend/node_modules/
frontend/dist/
frontend/src-tauri/target/
```

These are **not** in the same category:

```text
original recordings
canonical transcript JSON
research SQLite state
human-authored notes/tags/collections
saved searches
```

Do not solve a development-tool problem by deleting product evidence or durable research.

## The short recovery recipe

If you do not know where to start and your Git working tree is understood/safe:

```bash
# repository root
uv sync --locked --extra transcription

cd frontend
rm -rf node_modules
npm ci
npm run check:tauri-versions
npm run doctor:desktop
npm run tauri dev
```

For UI-only work, the much smaller recipe is:

```bash
cd frontend
npm ci
npm run doctor:desktop -- --mode=mock
npm run dev:mock
```

That separation is intentional. Frontend visual work should not require a researcher, UI
contributor, or first-time developer to install a transcription runtime just to see a
button.
