import { useEffect, useMemo, useState } from "react";

import {
  createDesktopClient,
  type LibraryLocation,
  type LocationKind,
  type ProcessingPolicy,
} from "./api/desktop";

const client = createDesktopClient();

type Theme = "archive" | "midnight";
type SelectionType = "files" | "folder" | null;

function basename(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).at(-1) ?? path;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

export function App() {
  const [theme, setTheme] = useState<Theme>("archive");
  const [purpose, setPurpose] = useState<LocationKind>("recording-source");
  const [selectionType, setSelectionType] = useState<SelectionType>(null);
  const [selectedPaths, setSelectedPaths] = useState<string[]>([]);
  const [remember, setRemember] = useState(false);
  const [automatic, setAutomatic] = useState(false);
  const [locations, setLocations] = useState<LibraryLocation[]>([]);
  const [discovered, setDiscovered] = useState<Array<{ path: string; size: number }>>([]);
  const [status, setStatus] = useState("Choose recordings or an existing transcript library to begin.");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    void client
      .listLocations()
      .then(setLocations)
      .catch(() => setStatus("EchoFlow is ready for a new local import."));
  }, []);

  const canRemember = selectionType === "folder" && selectedPaths.length === 1;
  const policy: ProcessingPolicy = automatic ? "automatic" : "manual";
  const actionLabel = remember ? "Remember this folder" : "Use this selection";
  const selectedTitle = useMemo(() => {
    if (selectedPaths.length === 0) return "Nothing selected yet";
    if (selectedPaths.length === 1) return basename(selectedPaths[0] ?? "");
    return `${selectedPaths.length} files selected`;
  }, [selectedPaths]);

  async function chooseFiles() {
    setError(null);
    const paths = await client.chooseFiles(purpose);
    if (paths.length === 0) return;
    setSelectionType("files");
    setSelectedPaths(paths);
    setRemember(false);
    setAutomatic(false);
    setStatus("This one-time selection stays local and is not remembered as a watched location.");
  }

  async function chooseFolder() {
    setError(null);
    const path = await client.chooseFolder();
    if (!path) return;
    setSelectionType("folder");
    setSelectedPaths([path]);
    setRemember(false);
    setAutomatic(false);
    setStatus("Choose whether EchoFlow should use this folder once or remember it for future discovery.");
  }

  async function applySelection() {
    if (selectedPaths.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      if (!remember) {
        setStatus(
          purpose === "recording-source"
            ? "Ready for transcription planning. EchoFlow has not saved a folder permission."
            : "Ready for one-time transcript import. EchoFlow has not saved a folder permission.",
        );
        return;
      }

      const path = selectedPaths[0];
      if (!path) return;
      await client.rememberLocation(path, purpose, purpose === "recording-source" ? policy : "manual");
      setLocations(await client.listLocations());
      if (purpose === "recording-source") {
        const report = await client.discoverRecordings();
        setDiscovered(report.recordings.map((item) => ({ path: item.path, size: item.size_bytes })));
        setStatus(
          `Folder remembered. ${report.recordings.length} recording${report.recordings.length === 1 ? "" : "s"} discovered; nothing was transcribed automatically by this action.`,
        );
      } else {
        await client.refreshTranscriptLocations();
        setStatus("Transcript library remembered and reconciled with EchoFlow's local index.");
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "EchoFlow could not add this location safely.");
    } finally {
      setBusy(false);
    }
  }

  function switchPurpose(next: LocationKind) {
    setPurpose(next);
    setSelectionType(null);
    setSelectedPaths([]);
    setRemember(false);
    setAutomatic(false);
    setDiscovered([]);
    setError(null);
  }

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true">E</div>
          <div>
            <p className="brand-name">EchoFlow</p>
            <p className="brand-subtitle">Private evidence workspace</p>
          </div>
        </div>

        <nav className="nav-list" aria-label="Workspace">
          <button className="nav-item nav-item-active" type="button" aria-current="page">
            <span aria-hidden="true">＋</span> Add evidence
          </button>
          <button className="nav-item" type="button" disabled>
            <span aria-hidden="true">⌕</span> Library
          </button>
          <button className="nav-item" type="button" disabled>
            <span aria-hidden="true">✦</span> Research
          </button>
        </nav>

        <div className="privacy-note">
          <span className="privacy-dot" aria-hidden="true" />
          <div>
            <strong>Local by default</strong>
            <p>Your recordings stay where you put them.</p>
          </div>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Evidence intake</p>
            <h1>Bring your recordings home.</h1>
          </div>
          <div className="theme-switch" role="group" aria-label="Appearance">
            <button
              type="button"
              className={theme === "archive" ? "theme-active" : ""}
              aria-pressed={theme === "archive"}
              onClick={() => setTheme("archive")}
            >
              Archive
            </button>
            <button
              type="button"
              className={theme === "midnight" ? "theme-active" : ""}
              aria-pressed={theme === "midnight"}
              onClick={() => setTheme("midnight")}
            >
              Midnight
            </button>
          </div>
        </header>

        <section className="intro-copy" aria-labelledby="intake-title">
          <div>
            <p className="section-kicker">01 · Choose what EchoFlow should know about</p>
            <h2 id="intake-title">Add local evidence without giving up custody.</h2>
          </div>
          <p>
            Select individual files for a one-time job, or remember a research folder so EchoFlow can discover new material when you ask it to refresh.
          </p>
        </section>

        <section className="intake-card" aria-label="Import controls">
          <div className="purpose-tabs" role="tablist" aria-label="Evidence type">
            <button
              type="button"
              role="tab"
              aria-selected={purpose === "recording-source"}
              className={purpose === "recording-source" ? "tab-active" : ""}
              onClick={() => switchPurpose("recording-source")}
            >
              Recordings
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={purpose === "transcript-library"}
              className={purpose === "transcript-library" ? "tab-active" : ""}
              onClick={() => switchPurpose("transcript-library")}
            >
              Existing transcripts
            </button>
          </div>

          <div className="picker-grid">
            <button className="picker-card" type="button" onClick={() => void chooseFiles()}>
              <span className="picker-icon" aria-hidden="true">↥</span>
              <span className="picker-title">Choose files</span>
              <span className="picker-detail">
                {purpose === "recording-source" ? "Audio or video, one or many" : "Canonical EchoFlow JSON"}
              </span>
            </button>
            <button className="picker-card" type="button" onClick={() => void chooseFolder()}>
              <span className="picker-icon" aria-hidden="true">⌑</span>
              <span className="picker-title">Choose folder</span>
              <span className="picker-detail">Use once or remember for later</span>
            </button>
          </div>

          <div className="selection-panel" aria-live="polite">
            <div className="selection-heading">
              <div>
                <p className="mini-label">Current selection</p>
                <h3>{selectedTitle}</h3>
              </div>
              {selectionType && <span className="selection-badge">{selectionType}</span>}
            </div>
            {selectedPaths.length > 0 && (
              <ul className="path-list" aria-label="Selected local paths">
                {selectedPaths.slice(0, 4).map((path) => (
                  <li key={path}>{path}</li>
                ))}
                {selectedPaths.length > 4 && <li>+ {selectedPaths.length - 4} more</li>}
              </ul>
            )}
          </div>

          {canRemember && (
            <fieldset className="retention-choice">
              <legend>How should EchoFlow use this location?</legend>
              <label className={!remember ? "choice-card choice-active" : "choice-card"}>
                <input
                  type="radio"
                  name="location-retention"
                  checked={!remember}
                  onChange={() => {
                    setRemember(false);
                    setAutomatic(false);
                  }}
                />
                <span>
                  <strong>Just this time</strong>
                  <small>Use the selection now. Do not save the folder as a library permission.</small>
                </span>
              </label>
              <label className={remember ? "choice-card choice-active" : "choice-card"}>
                <input
                  type="radio"
                  name="location-retention"
                  checked={remember}
                  onChange={() => setRemember(true)}
                />
                <span>
                  <strong>Remember this folder</strong>
                  <small>Revisit this location on explicit refresh and normal application lifecycle points.</small>
                </span>
              </label>
            </fieldset>
          )}

          {remember && purpose === "recording-source" && (
            <details className="advanced-card">
              <summary>Advanced processing policy</summary>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={automatic}
                  onChange={(event) => setAutomatic(event.target.checked)}
                />
                <span>
                  <strong>Automatically process newly discovered recordings</strong>
                  <small>
                    Explicit opt-in. Discovery itself still does not transcribe, copy, hash, or modify recordings.
                  </small>
                </span>
              </label>
            </details>
          )}

          <div className="action-row">
            <p className="status-copy" role="status">{status}</p>
            <button
              className="primary-action"
              type="button"
              disabled={selectedPaths.length === 0 || busy}
              onClick={() => void applySelection()}
            >
              {busy ? "Working…" : actionLabel}
            </button>
          </div>
          {error && <p className="error-banner" role="alert">{error}</p>}
        </section>

        <section className="lower-grid" aria-label="Import overview">
          <article className="info-card">
            <p className="mini-label">Remembered locations</p>
            <strong className="metric">{locations.length}</strong>
            <p>Private app preferences only. Forgetting one never deletes the files inside it.</p>
          </article>
          <article className="info-card">
            <p className="mini-label">Discovered recordings</p>
            <strong className="metric">{discovered.length}</strong>
            <p>
              {discovered.length === 0
                ? "Discovery is separate from processing."
                : `${basename(discovered[0]?.path ?? "")} · ${formatBytes(discovered[0]?.size ?? 0)} and ${Math.max(0, discovered.length - 1)} more`}
            </p>
          </article>
          <article className="info-card provenance-card">
            <p className="mini-label">Custody rule</p>
            <strong>Originals stay original.</strong>
            <p>Selecting media does not move it into a hidden EchoFlow vault.</p>
          </article>
        </section>
      </main>
    </div>
  );
}
