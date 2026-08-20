import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const frontendDir = resolve(scriptDir, "..");
const packageJson = JSON.parse(readFileSync(resolve(frontendDir, "package.json"), "utf8"));
const expected = JSON.parse(readFileSync(resolve(frontendDir, "tauri-versions.json"), "utf8"));
const cargoToml = readFileSync(resolve(frontendDir, "src-tauri", "Cargo.toml"), "utf8");
const cargoLock = readFileSync(resolve(frontendDir, "src-tauri", "Cargo.lock"), "utf8");

function fail(message) {
  console.error(`Tauri version check failed: ${message}`);
  process.exitCode = 1;
}

function cargoVersion(name) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const tablePattern = new RegExp(
    `^\\s*${escaped}\\s*=\\s*\\{[^}]*version\\s*=\\s*"([^"]+)"[^}]*\\}`,
    "m",
  );
  const simplePattern = new RegExp(`^\\s*${escaped}\\s*=\\s*"([^"]+)"`, "m");
  const match = cargoToml.match(tablePattern) ?? cargoToml.match(simplePattern);
  return match?.[1]?.replace(/^=/, "") ?? null;
}

function lockVersion(name) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(
    `\\[\\[package\\]\\]\\nname = "${escaped}"\\nversion = "([^"]+)"`,
    "m",
  );
  return cargoLock.match(pattern)?.[1] ?? null;
}

function majorMinor(version) {
  const match = /^(\d+)\.(\d+)\.(\d+)$/.exec(version ?? "");
  return match ? `${match[1]}.${match[2]}` : null;
}

const exactChecks = [
  ["@tauri-apps/api", packageJson.dependencies?.["@tauri-apps/api"], expected.jsApi],
  ["@tauri-apps/cli", packageJson.devDependencies?.["@tauri-apps/cli"], expected.cli],
  ["@tauri-apps/plugin-dialog", packageJson.dependencies?.["@tauri-apps/plugin-dialog"], expected.dialog],
  ["Rust tauri", cargoVersion("tauri"), expected.rustCore],
  ["Rust tauri-plugin-dialog", cargoVersion("tauri-plugin-dialog"), expected.dialog],
  ["Rust tauri-build", cargoVersion("tauri-build"), expected.build],
  ["locked tauri", lockVersion("tauri"), expected.rustCore],
  ["locked tauri-runtime", lockVersion("tauri-runtime"), expected.rustRuntime],
  ["locked tauri-runtime-wry", lockVersion("tauri-runtime-wry"), expected.rustRuntimeWry],
  ["locked tauri-plugin-dialog", lockVersion("tauri-plugin-dialog"), expected.dialog],
  ["locked tauri-build", lockVersion("tauri-build"), expected.build],
];

for (const [label, actual, wanted] of exactChecks) {
  if (actual !== wanted) {
    fail(`${label} is ${actual ?? "missing"}; expected exact version ${wanted}`);
  }
}

const pairedChecks = [
  ["Tauri core", expected.jsApi, expected.rustCore],
  ["dialog plugin", packageJson.dependencies?.["@tauri-apps/plugin-dialog"], cargoVersion("tauri-plugin-dialog")],
];

for (const [label, jsVersion, rustVersion] of pairedChecks) {
  if (majorMinor(jsVersion) === null || majorMinor(rustVersion) === null) {
    fail(`${label} versions must be full semantic versions`);
  } else if (majorMinor(jsVersion) !== majorMinor(rustVersion)) {
    fail(
      `${label} JavaScript ${jsVersion} and Rust ${rustVersion} must share a major/minor release, matching Tauri CLI compatibility rules`,
    );
  }
}

if (!process.exitCode) {
  console.log(
    `Tauri version family is aligned: JS API ${expected.jsApi}, Rust core ${expected.rustCore}, runtime ${expected.rustRuntime}, wry runtime ${expected.rustRuntimeWry}, CLI ${expected.cli}, dialog ${expected.dialog}, build ${expected.build}.`,
  );
}
