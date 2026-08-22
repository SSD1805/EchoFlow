# Desktop development prerequisites 🖥️

Scholion's packaged desktop application is intended for **normal users who install and run
an application**. Rust, Node.js, npm, Cargo, Vite, native SDKs, and the Tauri CLI are
source-build tools. They are not intended to become end-user prerequisites.

Until signed installers exist, contributors can choose the smallest development mode that
matches what they are trying to do. Source builds are exercised in CI on Linux, macOS, and
Windows.

## Choose a mode first

| I want to… | Start with | Required layers |
|---|---|---|
| inspect or work on the React UI with fake data | `npm run dev:mock` | Node + npm |
| run the real native Scholion window | `npm run tauri dev` | Node/npm + Rust/Cargo + the native build/webview stack for your OS; Python for backend actions |
| transcribe real media from source | native app or CLI processing flow | Python 3.12/uv + FFmpeg/FFprobe + a managed transcription model, in addition to the relevant UI/native layers |

A transcription model is not required to start the browser mock or render the native
window. FFmpeg is not required merely to render the window. Rust is not required for
browser-only UI work.

If you are unsure what your machine has, from `frontend/` run:

```bash
npm run doctor:desktop
```

For browser-only work:

```bash
npm run doctor:desktop -- --mode=mock
```

The doctor reports the platform and checks the prerequisites it can inspect safely. It does
not install software or change your machine. The detailed symptom-by-symptom recovery guide
is **[Desktop source-build troubleshooting](troubleshooting.md)**.

## Versions that are part of the source-build contract

The repository is the authority for supported tool versions:

- Python: `>=3.12,<3.13` from `pyproject.toml`;
- Node.js: `^20.19.0 || >=22.12.0` from `frontend/package.json`;
- Rust: stable toolchain, with the dependency graph locked by `frontend/src-tauri/Cargo.lock`;
- JavaScript dependencies: locked by `frontend/package-lock.json`.

Check the tools visible to your shell before debugging application code:

```bash
python --version
uv --version
node --version
npm --version
cargo --version
rustc --version
```

On Windows, `py -3.12 --version` can be a more reliable way to confirm the intended Python
installation when several Python versions are registered.

## What installs where

`npm ci` is project-local by default. From `frontend/`, it installs the exact dependency
graph from `package-lock.json` into:

```text
frontend/node_modules/
```

That is not a global machine install. Global npm installation requires an explicit flag such
as `npm install -g ...`; Scholion's development workflow does not require it.

`uv sync` creates or updates Scholion's repository-local Python environment:

```text
.venv/
```

On macOS and Linux the interpreter is normally `.venv/bin/python`. On Windows it is normally
`.venv\Scripts\python.exe`.

Cargo downloads Rust packages into Cargo's normal user cache. Scholion's disposable native
build output lives under:

```text
frontend/src-tauri/target/
```

The application repository commits `frontend/src-tauri/Cargo.lock` so Rust dependency
resolution is reproducible even though Cargo's package cache itself is shared.

## Browser-only React development on any platform

This is the smallest path and is the right choice if you only want to inspect the current
frontend or work on presentation/interactions.

macOS/Linux shell:

```bash
git clone https://github.com/SSD1805/Scholion.git
cd Scholion/frontend
npm ci
npm run doctor:desktop -- --mode=mock
npm run dev:mock
```

Windows PowerShell:

```powershell
git clone https://github.com/SSD1805/Scholion.git
Set-Location Scholion\frontend
npm ci
npm run doctor:desktop -- --mode=mock
npm run dev:mock
```

`dev:mock` opens the Vite app with explicit `?e2e=1` fake local data. Mock mode is opt-in so
an ordinary browser can never silently impersonate the real Tauri/Python authority.

If PowerShell refuses to run `npm.ps1` because of local execution policy, use the executable
shim that ships with Node rather than weakening machine-wide policy:

```powershell
npm.cmd ci
npm.cmd run doctor:desktop -- --mode=mock
npm.cmd run dev:mock
```

If you run plain `npm run dev` in an ordinary browser, Scholion shows a development-mode
notice instead of the real workspace. Plain `dev` remains the Vite server used internally by
`tauri dev`.

# Native Tauri source development

The common sequence is the same on all three operating systems:

1. install the OS-native compiler/webview prerequisites;
2. install a supported Node.js runtime and stable Rust toolchain;
3. make Python 3.12 and `uv` available;
4. create the locked Python environment from the repository root;
5. install the locked frontend graph from `frontend/`;
6. run the desktop doctor;
7. launch `npm run tauri dev`.

The OS-specific prerequisite in step 1 is important. npm and Cargo can download project
dependencies, but they cannot manufacture Apple's SDK, Microsoft's C++ toolchain, or Linux
WebKitGTK development libraries.

## macOS source build

Scholion's CI exercises the source tree on current macOS arm64 runners. Intel source builds
use the same toolchain shape, but keep the architecture of Node, Python, and Rust consistent
with each other when possible.

### 1. Install or verify Apple's build tools

Tauri uses the macOS native webview and Apple toolchain. Install the Xcode Command Line Tools:

```bash
xcode-select --install
```

If they are already installed, macOS will say so. Verify the active developer tools instead
of repeatedly reinstalling them:

```bash
xcode-select -p
xcrun --find clang
```

A valid `xcrun --find clang` result is a stronger signal than merely having an `xcode-select`
command on PATH.

### 2. Verify the language runtimes

```bash
node --version
npm --version
cargo --version
rustc --version
python3.12 --version
uv --version
```

Use stable Rust. If you use `rustup`, verify the selected toolchain with:

```bash
rustup show active-toolchain
```

### 3. Check architecture on Apple Silicon when native dependencies behave strangely

```bash
uname -m
node -p "process.arch"
python3.12 -c "import platform; print(platform.machine())"
rustc -vV
```

On an Apple Silicon machine the simplest source-build path is normally arm64 throughout.
Running an x86_64 Node process under Rosetta while Python/Rust are arm64, or the reverse, can
produce linker or native-wheel failures that look unrelated to architecture.

### 4. Create Scholion's Python environment

From the repository root:

```bash
uv sync --locked --extra transcription
.venv/bin/python -c "import scholion; print('Scholion import OK')"
```

### 5. Install frontend dependencies and check the native build

```bash
cd frontend
npm ci
npm run doctor:desktop
cargo check --locked --manifest-path src-tauri/Cargo.toml
```

The doctor verifies the Apple developer tools in addition to the common prerequisites.

### 6. Install media tools when you want to process real recordings

Scholion needs both `ffmpeg` and `ffprobe` for real media processing. Verify them first:

```bash
ffmpeg -version
ffprobe -version
```

If you already use Homebrew, one installation path is:

```bash
brew install ffmpeg
```

Homebrew is not a Scholion requirement. Any trusted installation that provides compatible
`ffmpeg` and `ffprobe` executables on PATH is acceptable for a source build.

### 7. Launch the native app

```bash
npm run tauri dev
```

Current accelerated transcription support is CUDA/NVIDIA-oriented. An Apple GPU is therefore
not currently advertised as a supported transcription accelerator by Scholion; CPU planning
on a Mac is expected behavior, not evidence that the machine-readiness screen failed.

## Windows source build

Use a normal PowerShell session unless a tool's installer specifically requires elevation.
Scholion does not require Administrator privileges just to run the source checkout after the
native prerequisites are installed.

### 1. Install the Microsoft native toolchain

Install **Visual Studio 2022 Build Tools** (or Visual Studio 2022) with:

- the **Desktop development with C++** workload;
- an MSVC v143 C++ build toolset; and
- a current Windows SDK.

Tauri also uses the Microsoft Edge **WebView2 Runtime**. It is present on most supported
Windows installations. If Tauri reports that WebView2 is unavailable, repair or install the
Evergreen WebView2 Runtime rather than adding a JavaScript webview package to the repository.

After installing Visual Studio Build Tools, a new shell is often necessary before newly
installed tooling is discoverable.

### 2. Verify the language runtimes in PowerShell

```powershell
node --version
npm --version
cargo --version
rustc --version
py -3.12 --version
uv --version
Get-Command cargo
```

A normal PowerShell session does not always put `link.exe` directly on PATH even when Cargo
can locate the Visual Studio installation. `npm run doctor:desktop` treats that condition as
a warning. The authoritative test is the locked native compile:

```powershell
cargo check --locked --manifest-path frontend\src-tauri\Cargo.toml
```

If that command reports `linker 'link.exe' not found`, repair the Visual Studio C++ workload
or Windows SDK rather than installing an unrelated linker.

### 3. Create Scholion's Python environment

From the repository root:

```powershell
uv sync --locked --extra transcription
.\.venv\Scripts\python.exe -c "import scholion; print('Scholion import OK')"
```

The Tauri debug host automatically prefers this repository environment. Activation is not
required.

### 4. Install frontend dependencies and run the doctor

```powershell
Set-Location frontend
npm ci
npm run doctor:desktop
```

If PowerShell blocks `npm.ps1`, use:

```powershell
npm.cmd ci
npm.cmd run doctor:desktop
```

That works around the shell script policy without changing the machine's execution policy.

### 5. Install media tools when you want to process real recordings

Both executables must resolve from the same shell that launches Scholion:

```powershell
Get-Command ffmpeg
Get-Command ffprobe
ffmpeg -version
ffprobe -version
```

If `Get-Command` cannot find them, install a trusted Windows FFmpeg distribution and add the
directory containing `ffmpeg.exe` and `ffprobe.exe` to PATH. Open a new PowerShell session
after changing PATH.

### 6. Launch the native app

```powershell
npm run tauri dev
```

Or, when PowerShell script policy requires the executable shim:

```powershell
npm.cmd run tauri dev
```

On Windows, Scholion's current accelerated path recognizes supported NVIDIA/CUDA hardware
when the required NVIDIA tooling is available. If it is not, the planner should fall back to
a safe CPU strategy rather than assuming GPU support.

## Linux source build

Linux Tauri uses WebKitGTK, so Linux has additional package-manager and display-stack
requirements that do not apply to macOS or Windows.

On Arch/Manjaro, one Rust setup is:

```bash
sudo pacman -S rustup
rustup default stable
```

A typical Tauri 2 development set is:

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
  librsvg \
  ffmpeg
```

Package names can evolve with distributions. The desktop doctor checks that the critical
WebKitGTK/GTK development interfaces are actually discoverable rather than assuming a
package command succeeded.

From the repository root:

```bash
uv sync --locked --extra transcription
cd frontend
npm ci
npm run doctor:desktop
cargo check --locked --manifest-path src-tauri/Cargo.toml
npm run tauri dev
```

Most Wayland systems work normally, but some compositor/GPU/WebKitGTK combinations can
produce a protocol-level display failure such as:

```text
Error 71: Protocol error, dispatching to Wayland display
```

That is a Linux display-stack compatibility issue, not a reason to modify Scholion's evidence
or Python state. The troubleshooting guide explains command-scoped DMABUF and X11/XWayland
fallbacks.

## Python backend for real application actions

The Rust host delegates application/evidence rules to the local Python bridge. In a source
checkout it automatically prefers the repository's `.venv` when present.

The common setup command from the repository root is:

```bash
uv sync --locked --extra transcription
```

You normally do **not** need to activate that virtual environment. Advanced users can
explicitly override the interpreter with `SCHOLION_PYTHON=/path/to/python` on macOS/Linux or
an equivalent environment variable in PowerShell. Do not set the override globally unless
you actually want future Scholion source builds to use that interpreter.

A transcription model is a later processing prerequisite. Install it from Processing Center
or the CLI when you actually want to transcribe, not merely to prove the native window opens.

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

If 5173 is occupied, stop the old development process and rerun. The troubleshooting guide
contains macOS, Windows PowerShell, and Linux commands for identifying the listener without
blindly killing unrelated processes.

## Native host smoke

CI compiles the native Tauri host in addition to TypeScript/Vite checks and runs Python smoke
tests on macOS and Windows as well as the main Linux quality suite. Frontend compilation alone
cannot catch missing native assets, invalid Rust configuration, Tauri version drift, or
platform-specific Python/media failures.

The checked-in `frontend/src-tauri/icons/icon.png` is required by Tauri's generated context.
Do not delete or rename native assets merely because the browser frontend does not import
them.

## Clean-up by platform

Project-local JavaScript dependencies and Rust build output are disposable.

macOS/Linux:

```bash
rm -rf frontend/node_modules
cargo clean --manifest-path frontend/src-tauri/Cargo.toml
```

Windows PowerShell:

```powershell
Remove-Item -Recurse -Force frontend\node_modules
cargo clean --manifest-path frontend\src-tauri\Cargo.toml
```

Then reinstall the locked JavaScript graph from `frontend/` with `npm ci`.

Do **not** delete `frontend/src-tauri/Cargo.lock` as routine cleanup. It is part of the
reviewed build contract. Neither cleanup command deletes Scholion recordings, canonical
transcripts, or durable research state. Product data and build artifacts live under different
custody rules.
