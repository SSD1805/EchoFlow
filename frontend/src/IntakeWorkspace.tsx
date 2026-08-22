import { useEffect, useMemo, useState } from "react";

import type {
  DesktopClient,
  LibraryLocation,
  LocationKind,
  ProcessingPolicy,
} from "./api/desktop";
import { WorkspaceHeader, type Theme } from "./components/WorkspaceHeader";

interface IntakeWorkspaceProps {
  client: DesktopClient;
  theme: Theme;
  onThemeChange: (theme: Theme) => void;
}

type SelectionType = "files" | "folder" | null;

function basename(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).at(-1) ?? path;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

export function IntakeWorkspace({ client, theme, onThemeChange }: IntakeWorkspaceProps) {
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
    void client
      .listLocations()
      .then(setLocations)
      .catch(() => setStatus("Scholion is ready for a new local import."));
  }, [client]);

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
    setStatus("Choose whether Scholion should use this folder once or remember it for future discovery.");
  }

  async function applySelection() {
    if (selectedPaths.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      if (!remember) {
        setStatus(
          purpose === "recording-source"
            ? "Ready for transcription planning. Scholion has not saved a folder permission."
            : "Ready for one-time transcript import. Scholion has not saved a folder permission.",
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
        setStatus("Transcript library remembered and reconciled with Scholion's local index.");
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Scholion could not add this location safely.");
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
    <>
      <WorkspaceHeader
        eyebrow="Evidence intake"
        title="Bring your recordings home."
        theme={theme}
        onThemeChange={onThemeChange}
      />

      <section className="intro-copy" aria-labelledby="intake-title">
        <div>
          <p className="section-kicker">01 · Choose what Scholion should know about</p>
          <h2 id="intake-title">Add local evidence without giving up custody.</h2>
        </div>
        <p>
          Select individual files for a one-time job, or remember a research folder so Scholion can discover new material when you ask it to refresh.
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
              {purpose === "recording-source" ? "Audio or video, one or many" : "Canonical Scholion JSON"}
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
            <legend>How should Scholion use this location?</legend>
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
          <p>Selecting media does not move it into a hidden Scholion vault.</p>
        </article>
      </section>
    </>
  );
}
