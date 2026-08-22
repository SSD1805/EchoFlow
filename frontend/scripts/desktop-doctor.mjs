import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, isAbsolute, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const frontendDir = resolve(scriptDir, "..");
const repoDir = resolve(frontendDir, "..");
const requestedMode = process.argv.find((arg) => arg.startsWith("--mode="))?.split("=", 2)[1];
const mode = requestedMode ?? "native";

if (!new Set(["mock", "native"]).has(mode)) {
  console.error("Usage: npm run doctor:desktop -- --mode=mock|native");
  process.exit(2);
}

let failures = 0;
let warnings = 0;

function run(command, args = []) {
  return spawnSync(command, args, { encoding: "utf8", shell: false });
}

function firstLine(value) {
  return value.trim().split(/\r?\n/, 1)[0] ?? "";
}

function pass(label, detail) {
  console.log(`✓ ${label}${detail ? `: ${detail}` : ""}`);
}

function warn(label, detail, remedy) {
  warnings += 1;
  console.log(`! ${label}: ${detail}`);
  if (remedy) console.log(`  → ${remedy}`);
}

function fail(label, detail, remedy) {
  failures += 1;
  console.log(`✗ ${label}: ${detail}`);
  if (remedy) console.log(`  → ${remedy}`);
}

function commandCheck(command, args, label, remedy) {
  const result = run(command, args);
  if (result.status === 0) {
    pass(label, firstLine(result.stdout || result.stderr));
    return true;
  }
  fail(label, `${command} is unavailable or failed to run`, remedy);
  return false;
}

function supportedNodeVersion() {
  const [major = 0, minor = 0] = process.versions.node.split(".").map(Number);
  return (major === 20 && minor >= 19) || (major === 22 && minor >= 12) || major > 22;
}

function looksLikePath(value) {
  return isAbsolute(value) || value.includes("/") || value.includes("\\");
}

function checkPythonBackend(command, source) {
  if (looksLikePath(command) && !existsSync(command)) {
    fail(
      "Python backend",
      `${source} points to a file that does not exist: ${command}`,
      source === "SCHOLION_PYTHON"
        ? "Fix or unset SCHOLION_PYTHON, or create the repository environment with: uv sync --locked --extra transcription"
        : "From the repository root run: uv sync --locked --extra transcription",
    );
    return;
  }

  const importCheck = run(command, [
    "-c",
    "import scholion; print('Scholion Python backend import is ready')",
  ]);
  if (importCheck.status === 0) {
    pass("Python backend", `${firstLine(importCheck.stdout)} (${source})`);
    return;
  }

  const detail = importCheck.error?.code === "ENOENT"
    ? `${source} could not be executed: ${command}`
    : `${source} cannot import scholion`;
  fail(
    "Python backend",
    detail,
    source === "SCHOLION_PYTHON"
      ? "Fix or unset SCHOLION_PYTHON, or create the repository environment with: uv sync --locked --extra transcription"
      : "From the repository root run: uv sync --locked --extra transcription",
  );
}

console.log("Scholion desktop doctor");
console.log(`Mode: ${mode === "mock" ? "browser mock" : "native Tauri source build"}\n`);

if (supportedNodeVersion()) {
  pass("Node.js", `v${process.versions.node} matches frontend/package.json`);
} else {
  fail(
    "Node.js",
    `v${process.versions.node} is outside Scholion's supported range (^20.19.0 or >=22.12.0)`,
    "Install a supported Node.js release, then run npm ci again.",
  );
}
commandCheck("npm", ["--version"], "npm", "Install npm with the supported Node.js runtime.");

const packageLock = resolve(frontendDir, "package-lock.json");
if (existsSync(packageLock)) {
  pass("JavaScript lockfile", "frontend/package-lock.json is present");
} else {
  fail(
    "JavaScript lockfile",
    "package-lock.json is missing",
    "Restore it from Git; do not replace npm ci with an unlocked install.",
  );
}

if (existsSync(resolve(frontendDir, "node_modules"))) {
  pass("Project-local JavaScript dependencies", "frontend/node_modules exists");
} else {
  fail(
    "Project-local JavaScript dependencies",
    "frontend/node_modules is missing",
    "From frontend/, run: npm ci",
  );
}

const versionCheck = run(process.execPath, [resolve(scriptDir, "check-tauri-versions.mjs")]);
if (versionCheck.status === 0) {
  pass("Tauri version family", firstLine(versionCheck.stdout));
} else {
  fail(
    "Tauri version family",
    firstLine(versionCheck.stderr || versionCheck.stdout) ||
      "JavaScript and Rust Tauri versions are not aligned",
    "Restore package.json, tauri-versions.json, and src-tauri/Cargo.toml from the same Git revision.",
  );
}

if (mode === "mock") {
  console.log(
    "\nBrowser mock needs no Python, Rust, Cargo, FFmpeg, WebKitGTK, or transcription model.",
  );
  console.log("Start it with: npm run dev:mock");
} else {
  console.log("\nNative host checks");
  const cargoReady = commandCheck(
    "cargo",
    ["--version"],
    "Cargo",
    "Install a stable Rust toolchain, then restart your shell if PATH changed.",
  );
  commandCheck(
    "rustc",
    ["--version"],
    "Rust compiler",
    "Install a stable Rust toolchain.",
  );

  const cargoLock = resolve(frontendDir, "src-tauri", "Cargo.lock");
  if (existsSync(cargoLock)) {
    pass("Rust lockfile", "frontend/src-tauri/Cargo.lock is present");
  } else {
    fail(
      "Rust lockfile",
      "Cargo.lock is missing",
      "Restore the committed lockfile from Git. Scholion source builds are intentionally locked.",
    );
  }

  const icon = resolve(frontendDir, "src-tauri", "icons", "icon.png");
  if (existsSync(icon)) {
    pass("Native application icon", "src-tauri/icons/icon.png is present");
  } else {
    fail(
      "Native application icon",
      "Tauri's compile-time icon is missing",
      "Restore frontend/src-tauri/icons/icon.png from Git.",
    );
  }

  const overridePython = process.env.SCHOLION_PYTHON?.trim();
  const venvPython = process.platform === "win32"
    ? resolve(repoDir, ".venv", "Scripts", "python.exe")
    : resolve(repoDir, ".venv", "bin", "python");
  if (overridePython) {
    checkPythonBackend(overridePython, "SCHOLION_PYTHON");
  } else if (existsSync(venvPython)) {
    checkPythonBackend(venvPython, "repository .venv");
  } else {
    fail(
      "Python backend",
      "the repository .venv is missing",
      "From the repository root run: uv sync --locked --extra transcription",
    );
  }

  if (process.platform === "linux") {
    if (
      commandCheck(
        "pkg-config",
        ["--version"],
        "pkg-config",
        "Install pkg-config plus your distribution's Tauri Linux development prerequisites.",
      )
    ) {
      const webkit = run("pkg-config", ["--exists", "webkit2gtk-4.1", "gtk+-3.0"]);
      if (webkit.status === 0) {
        pass(
          "Linux WebKitGTK/GTK development libraries",
          "webkit2gtk-4.1 and gtk+-3.0 are discoverable",
        );
      } else {
        fail(
          "Linux WebKitGTK/GTK development libraries",
          "required native webview/build packages are not discoverable",
          "Install the Tauri Linux prerequisites for your distribution; Arch/Manjaro guidance is in docs/development/desktop-development.md.",
        );
      }
    }

    if (process.env.WAYLAND_DISPLAY) {
      pass("Display session", `Wayland detected (${process.env.WAYLAND_DISPLAY})`);
      warn(
        "Wayland compatibility",
        "WebKitGTK/GPU compositor combinations can occasionally terminate with protocol error 71",
        "If that exact error occurs, see docs/development/troubleshooting.md before changing global environment settings.",
      );
    } else if (process.env.DISPLAY) {
      pass("Display session", `X11/XWayland detected (${process.env.DISPLAY})`);
    } else {
      warn(
        "Display session",
        "no WAYLAND_DISPLAY or DISPLAY variable is visible",
        "A graphical Tauri window needs a desktop display session.",
      );
    }
  }

  if (cargoReady && existsSync(cargoLock)) {
    console.log("\nDeep native compile check (optional but authoritative):");
    console.log("  cargo check --locked --manifest-path src-tauri/Cargo.toml");
  }
}

console.log(
  `\nSummary: ${failures} failure${failures === 1 ? "" : "s"}, ${warnings} warning${warnings === 1 ? "" : "s"}.`,
);
if (failures > 0) {
  console.log(
    "Fix the failures above, then run the doctor again. The troubleshooting guide explains each class of failure.",
  );
  process.exitCode = 1;
} else {
  console.log(
    mode === "mock"
      ? "Browser mock prerequisites look ready."
      : "Native source-build prerequisites look ready.",
  );
}
