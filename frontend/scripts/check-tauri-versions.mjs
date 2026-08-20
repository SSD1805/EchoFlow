import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const frontendDir = resolve(scriptDir, "..");
const packageJson = JSON.parse(readFileSync(resolve(frontendDir, "package.json"), "utf8"));
const expected = JSON.parse(readFileSync(resolve(frontendDir, "tauri-versions.json"), "utf8"));
const cargoToml = readFileSync(resolve(frontendDir, "src-tauri", "Cargo.toml"), "utf8");

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

const checks = [
  ["@tauri-apps/api", packageJson.dependencies?.["@tauri-apps/api"], expected.core],
  ["@tauri-apps/cli", packageJson.devDependencies?.["@tauri-apps/cli"], expected.cli],
  ["@tauri-apps/plugin-dialog", packageJson.dependencies?.["@tauri-apps/plugin-dialog"], expected.dialog],
  ["Rust tauri", cargoVersion("tauri"), expected.core],
  ["Rust tauri-plugin-dialog", cargoVersion("tauri-plugin-dialog"), expected.dialog],
  ["Rust tauri-build", cargoVersion("tauri-build"), expected.build],
];

for (const [label, actual, wanted] of checks) {
  if (actual !== wanted) {
    fail(`${label} is ${actual ?? "missing"}; expected exact version ${wanted}`);
  }
}

if (!process.exitCode) {
  console.log(
    `Tauri version family is aligned: core ${expected.core}, CLI ${expected.cli}, dialog ${expected.dialog}, build ${expected.build}.`,
  );
}
