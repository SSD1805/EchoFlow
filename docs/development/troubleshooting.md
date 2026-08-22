# Desktop source-build troubleshooting 🧰

This page is for source-build failures on **macOS, Windows, and Linux**. The underlying
problem is usually one missing native tool, one stale dependency tree, one PATH mismatch, or
an operating-system-specific webview/build requirement.

Start by identifying **which development mode you are trying to run**. Scholion has three
layers and they intentionally do not share every prerequisite.

| Goal | Command | What you need |
|---|---|---|
| Inspect/click the React UI with fake data | `npm run dev:mock` | Node + npm only |
| Run the real native Tauri window | `npm run tauri dev` | Node/npm + Rust/Cargo + native OS compiler/webview requirements; Python for backend actions |
| Actually transcribe from source | native app or CLI processing flow | Python 3.12/uv + FFmpeg/FFprobe + an installed Scholion model, in addition to the relevant native layers |

A transcription model is **not** required merely to launch the UI. FFmpeg is **not** required
merely to render the native window. Rust and Python are **not** required for the browser
mock.

Before chasing an error manually, from `frontend/` run:

```bash
npm run doctor:desktop
```

For the browser-only mock:

```bash
npm run doctor:desktop -- --mode=mock
```

On Windows, if PowerShell blocks `npm.ps1`, use the Node executable shim without changing
machine-wide script policy:

```powershell
npm.cmd run doctor:desktop
```

The doctor reports all relevant checks instead of stopping at the first missing prerequisite.
It also prints the platform and architecture it sees.

For complete first-time setup, see **[Desktop development prerequisites](desktop-development.md)**.

## Platform jump table

| Platform | Native build stack | Most useful first checks |
|---|---|---|
| macOS | Apple Command Line Tools + native WKWebView | `xcode-select -p`, `xcrun --find clang`, `uname -m` |
| Windows | Visual Studio 2022 C++ Build Tools + Windows SDK + WebView2 | `cargo --version`, `cargo check --locked ...`, `Get-Command ffmpeg` |
| Linux | compiler/build tools + WebKitGTK/GTK | `pkg-config`, WebKitGTK check, display session |

The Linux-specific WebKitGTK and Wayland sections later in this document do **not** apply to
macOS or Windows.

## Start with a known-good checkout

From the repository root:

```bash
git status
```

On PowerShell the command is the same:

```powershell
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

The Python equivalent is `uv sync`, which creates or updates the repository-local `.venv`.
Cargo has a user-level package cache, while this app's disposable Rust build output lives
under `frontend/src-tauri/target/`.

---

# Symptom: `npm error Missing script: "dev:mock"`

## What it means

Your checkout does not contain the explicit browser-mock script yet, or you are running npm
from a directory whose `package.json` is not Scholion's `frontend/package.json`.

## Check on macOS/Linux

```bash
pwd
npm run
```

## Check on Windows PowerShell

```powershell
Get-Location
npm run
```

You should be inside the repository's `frontend/` directory, and the script list should
contain `dev:mock`.

## Fix

Update to a revision that contains the script, inspect local work first, then reinstall the
locked graph if needed:

```bash
cd /path/to/Scholion
git status
git pull
cd frontend
npm ci
npm run dev:mock
```

PowerShell uses the same Git/npm commands after `Set-Location` to the checkout.

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

## If you want the real native application

```bash
npm run doctor:desktop
npm run tauri dev
```

On Windows with a restrictive PowerShell script policy:

```powershell
npm.cmd run doctor:desktop
npm.cmd run tauri dev
```

---

# Symptom: the browser mock is blank or black

A truly blank browser mock usually means a JavaScript build/runtime error, a stale dev server,
or an older checkout.

1. Confirm you are in `frontend/`.
2. Stop old Vite/Tauri processes with `Ctrl+C` in the terminals that launched them.
3. Reinstall only the project-local JavaScript graph.

macOS/Linux:

```bash
rm -rf node_modules
npm ci
npm run dev:mock
```

Windows PowerShell:

```powershell
Remove-Item -Recurse -Force node_modules
npm ci
npm run dev:mock
```

If PowerShell blocks `npm.ps1`, substitute `npm.cmd` in those commands.

The `node_modules` directory is rebuildable developer state. Removing it does not touch
recordings, canonical transcripts, or research state.

---

# Symptom: `failed to run 'cargo metadata'` or Cargo is not found

Tauri tried to launch Cargo, but `cargo` was not installed or was not visible on PATH. A
“No such file or directory” message often refers to the **Cargo executable**, not to
Scholion's `Cargo.toml`.

macOS/Linux:

```bash
cargo --version
rustc --version
which cargo
```

Windows PowerShell:

```powershell
cargo --version
rustc --version
Get-Command cargo
```

Install a stable Rust toolchain, open a new shell if PATH changed, then rerun the checks.
Scholion's Tauri manifest is `frontend/src-tauri/Cargo.toml`. You do not need a global Tauri
CLI because the repository carries its Tauri CLI through npm.

---

# macOS: `xcrun`, `clang`, SDK, or linker errors

## What it usually means

Rust/Cargo is installed, but the Apple native compiler/SDK selected for the shell is missing
or unhealthy. npm cannot install Apple's native SDK for you.

## Check

```bash
xcode-select -p
xcrun --find clang
xcrun --show-sdk-path
```

If `xcode-select -p` or `xcrun --find clang` fails, install the Command Line Tools:

```bash
xcode-select --install
```

Then open a new terminal and rerun the checks. After a macOS/Xcode upgrade, an existing
Command Line Tools installation can occasionally need repair. Do not alter developer-directory
paths by guesswork. Confirm which installation actually exists before using `xcode-select`
to switch it.

Run the repository's authoritative native compile from the repository root:

```bash
cargo check --locked --manifest-path frontend/src-tauri/Cargo.toml
```

A failure here is more informative than a successful Vite build because it exercises the
native host.

---

# macOS: native-wheel or linker errors on Apple Silicon

## Why architecture matters

An Apple Silicon machine can run arm64 tools natively and x86_64 tools through Rosetta. A
mixed source-build stack can therefore contain an x86_64 Node process, arm64 Python, and an
arm64 Rust target without the mismatch being visually obvious.

## Check all four layers

```bash
uname -m
node -p "process.arch"
.venv/bin/python -c "import platform; print(platform.machine())"
rustc -vV
```

For the simplest Apple Silicon build, these should normally agree on arm64/aarch64. If one
runtime is x86_64 because it was installed under Rosetta, replace or intentionally align that
runtime rather than changing Scholion source code to accommodate an accidental mixed toolchain.

Current accelerated transcription support is CUDA/NVIDIA-oriented. Seeing CPU planning on a
Mac is expected; it is not an Apple-GPU detection failure.

---

# Windows: `linker 'link.exe' not found`, MSVC, or Windows SDK errors

## What it usually means

Rust is installed, but the Microsoft native C++ build toolchain needed by the Windows Tauri
host is missing or incomplete.

Install or modify **Visual Studio 2022 Build Tools** (or Visual Studio 2022) so it includes:

- **Desktop development with C++**;
- an MSVC v143 C++ toolset; and
- a current Windows SDK.

Open a new PowerShell session after installation.

## Check

```powershell
cargo --version
rustc --version
where.exe link.exe
cargo check --locked --manifest-path frontend\src-tauri\Cargo.toml
```

`where.exe link.exe` can fail in an ordinary PowerShell session even when Cargo can discover
Visual Studio through its normal tooling. That is why the desktop doctor reports it as a
warning rather than an automatic failure. The `cargo check --locked` result is authoritative.

Do not install a random Unix linker or switch Rust to the GNU Windows target just to make the
message disappear. Scholion's normal Windows path is the MSVC toolchain.

---

# Windows: WebView2 runtime error or native window cannot create its webview

Tauri uses Microsoft Edge WebView2 on Windows. The runtime is present on most supported
Windows installations, but it can be missing or damaged.

If the Tauri terminal reports a WebView2 initialization/runtime error, repair or install the
**Evergreen WebView2 Runtime**, then reopen the terminal and retry:

```powershell
Set-Location frontend
npm run tauri dev
```

This is an operating-system runtime issue. Do not add a browser package to `package.json` as
a substitute for the native WebView2 Runtime.

---

# Windows: `npm.ps1 cannot be loaded because running scripts is disabled`

## What it means

PowerShell is refusing the `.ps1` command shim generated by Node. This does not mean npm is
missing and it does not require changing the machine's execution policy.

## Check

```powershell
Get-Command npm.cmd
npm.cmd --version
```

## Run Scholion through the executable shim

```powershell
npm.cmd ci
npm.cmd run doctor:desktop
npm.cmd run tauri dev
```

This keeps the local PowerShell policy intact.

---

# Symptom: `found version mismatch Tauri packages`

Tauri has JavaScript packages **and** Rust crates. They are two halves of one desktop runtime.
Scholion declares the intended family in:

```text
frontend/tauri-versions.json
```

and freezes the Rust graph in `frontend/src-tauri/Cargo.lock`.

From `frontend/`:

```bash
npm run check:tauri-versions
cargo check --locked --manifest-path src-tauri/Cargo.toml
```

If the version check fails, `package.json`, `tauri-versions.json`, and
`src-tauri/Cargo.toml` may have come from different revisions or been locally modified.
Inspect `git status` before changing anything.

Do **not** globally upgrade/downgrade Tauri by trial and error, and do not delete `Cargo.lock`
to make `--locked` stop complaining.

---

# Symptom: `failed to open icon ... src-tauri/icons/icon.png`

Tauri reads native application assets at compile time. The React frontend does not import the
icon, so a Vite build can be healthy while the native host fails.

macOS/Linux from `frontend/`:

```bash
ls -l src-tauri/icons/icon.png
```

Windows PowerShell:

```powershell
Get-Item src-tauri\icons\icon.png
```

Restore the checked-in binary asset from Git if it is missing. Do not replace it with an empty
file or text placeholder.

---

# Symptom: `Scholion's local Python service is unavailable`

The native Rust host delegates application/evidence rules to the local Python bridge. In a
source checkout it prefers the repository's `.venv`. If that environment has not been
created, the native UI can launch while backend-backed actions fail.

From the repository root:

```bash
uv sync --locked --extra transcription
```

macOS/Linux verification:

```bash
.venv/bin/python -c "import scholion; print('Scholion import OK')"
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -c "import scholion; print('Scholion import OK')"
```

Scholion currently requires Python 3.12. If `uv sync` reports an incompatible interpreter,
verify the Python seen by your environment instead of editing the version constraint:

macOS/Linux:

```bash
python3.12 --version
```

Windows:

```powershell
py -3.12 --version
```

Then rerun the desktop doctor from `frontend/`.

### Advanced interpreter override

macOS/Linux for one launch:

```bash
SCHOLION_PYTHON=/path/to/python npm run tauri dev
```

Windows PowerShell for the current process:

```powershell
$env:SCHOLION_PYTHON = "C:\path\to\python.exe"
npm run tauri dev
```

Unset the variable after diagnosis if you do not want future launches to use it.

---

# Symptom: FFmpeg or FFprobe is missing

## What it affects

You can still inspect the browser mock and can usually render the native window, but Scholion
cannot probe/process real recordings without both tools.

macOS:

```bash
ffmpeg -version
ffprobe -version
```

If you use Homebrew, one installation path is `brew install ffmpeg`.

Windows PowerShell:

```powershell
Get-Command ffmpeg
Get-Command ffprobe
ffmpeg -version
ffprobe -version
```

If the commands are not found, install a trusted Windows FFmpeg distribution and add the
directory containing both executables to PATH. Open a new PowerShell session after modifying
PATH.

Linux:

```bash
ffmpeg -version
ffprobe -version
```

Install your distribution's FFmpeg package if either command is absent.

The desktop doctor treats missing media tools as warnings because they are not required to
merely render the app.

---

# Linux: WebKitGTK / GTK / `pkg-config` errors

A Tauri Linux app uses the operating system's WebKitGTK stack. npm can install JavaScript
packages and Cargo can download Rust crates, but neither installs Linux GTK/WebKit development
libraries.

```bash
pkg-config --version
pkg-config --exists webkit2gtk-4.1 gtk+-3.0 && echo "WebKitGTK/GTK found"
```

On Arch/Manjaro, a typical Tauri 2 development set is:

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

Package names can change across distribution releases. Use your distribution's current Tauri
2 prerequisites if a name changes rather than substituting unrelated packages.

---

# Linux: `Error 71: Protocol error, dispatching to Wayland display`

On Linux the Tauri webview is WebKitGTK. WebKitGTK, the GPU/DMABUF renderer, the Wayland
compositor, and the graphics driver all participate in drawing the window. Some combinations
can terminate at the Wayland protocol layer even when Scholion's React and Rust code are
valid.

This is a display-stack compatibility failure, not evidence that your transcript library or
Python environment is corrupt.

Run the doctor first. If its native prerequisites are healthy and Wayland is detected, try
these **one command at a time**.

Disable WebKitGTK's DMABUF renderer for one launch:

```bash
WEBKIT_DISABLE_DMABUF_RENDERER=1 npm run tauri dev
```

Diagnostic X11/XWayland launch:

```bash
GDK_BACKEND=x11 npm run tauri dev
```

Combine them only when needed:

```bash
GDK_BACKEND=x11 WEBKIT_DISABLE_DMABUF_RENDERER=1 npm run tauri dev
```

Use these as diagnosis/fallback, not global defaults.

---

# Symptom: `Port 5173 is already in use`

Tauri's development URL is fixed to `http://localhost:5173`. Scholion runs Vite with
`--strictPort` because silently moving Vite to 5174 would leave Tauri pointing at the wrong
process.

## macOS

```bash
lsof -nP -iTCP:5173 -sTCP:LISTEN
```

## Windows PowerShell

```powershell
Get-NetTCPConnection -LocalPort 5173 -State Listen | Select-Object LocalAddress,LocalPort,OwningProcess
Get-Process -Id <PID>
```

Replace `<PID>` only after reading the owning process from the first command.

## Linux

```bash
ss -ltnp | grep 5173
```

or:

```bash
lsof -i :5173
```

Stop the Vite/Tauri process you previously launched, normally with `Ctrl+C` in its original
terminal. Do not kill an unrelated process just because it uses the port.

---

# Symptom: npm dependencies seem stale or impossible

Use the lockfile as authority.

macOS/Linux from the repository root:

```bash
rm -rf frontend/node_modules
cd frontend
npm ci
npm run check:tauri-versions
```

Windows PowerShell:

```powershell
Remove-Item -Recurse -Force frontend\node_modules
Set-Location frontend
npm ci
npm run check:tauri-versions
```

Do not use `npm update` as a troubleshooting hammer. Updating dependencies is a source change
that should be reviewed and committed deliberately.

---

# Symptom: Rust build state seems stale or impossible

You may remove **build output** without removing the Rust lockfile.

macOS/Linux from the repository root:

```bash
cargo clean --manifest-path frontend/src-tauri/Cargo.toml
cargo check --locked --manifest-path frontend/src-tauri/Cargo.toml
```

Windows PowerShell:

```powershell
cargo clean --manifest-path frontend\src-tauri\Cargo.toml
cargo check --locked --manifest-path frontend\src-tauri\Cargo.toml
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

# Short recovery recipes

Use these only after `git status` is understood and local work is safe.

## macOS

```bash
# repository root
xcode-select -p
xcrun --find clang
uv sync --locked --extra transcription

cd frontend
rm -rf node_modules
npm ci
npm run check:tauri-versions
npm run doctor:desktop
cargo check --locked --manifest-path src-tauri/Cargo.toml
npm run tauri dev
```

## Windows PowerShell

```powershell
# repository root
uv sync --locked --extra transcription

Set-Location frontend
Remove-Item -Recurse -Force node_modules -ErrorAction SilentlyContinue
npm ci
npm run check:tauri-versions
npm run doctor:desktop
cargo check --locked --manifest-path src-tauri\Cargo.toml
npm run tauri dev
```

If PowerShell blocks `npm.ps1`, replace each `npm` with `npm.cmd`.

## Linux

```bash
# repository root
uv sync --locked --extra transcription

cd frontend
rm -rf node_modules
npm ci
npm run check:tauri-versions
npm run doctor:desktop
cargo check --locked --manifest-path src-tauri/Cargo.toml
npm run tauri dev
```

## UI-only recovery on any platform

The much smaller recipe is:

```bash
cd frontend
npm ci
npm run doctor:desktop -- --mode=mock
npm run dev:mock
```

On Windows, use `npm.cmd` when PowerShell script policy requires it.

That separation is intentional. Frontend visual work should not require a researcher, UI
contributor, or first-time developer to install a transcription runtime just to see a button.
