import "./development-mode.css";

export function DevelopmentModeNotice() {
  return (
    <main className="dev-mode-shell">
      <section className="dev-mode-card" aria-labelledby="dev-mode-title">
        <p className="section-kicker">Scholion source development</p>
        <h1 id="dev-mode-title">You opened the Vite server without a desktop host.</h1>
        <p className="dev-mode-lede">
          Nothing is broken. This browser tab does not have Tauri's native filesystem and
          Python bridge capabilities, so Scholion will not silently pretend that mock data is
          your real local workspace.
        </p>

        <div className="dev-mode-options">
          <article>
            <p className="mini-label">I only want to inspect the UI</p>
            <h2>Run the browser mock.</h2>
            <code>npm run dev:mock</code>
            <p>
              This uses clearly fake local data. It needs Node/npm only and does not require
              Python, Rust, Cargo, FFmpeg, WebKitGTK, or a transcription model.
            </p>
          </article>

          <article>
            <p className="mini-label">I want the real native application</p>
            <h2>Run the Tauri host.</h2>
            <code>npm run tauri dev</code>
            <p>
              This needs the native development prerequisites and Scholion's local Python
              environment for backend actions. Run <code>npm run doctor:desktop</code> first if
              you are unsure what is installed.
            </p>
          </article>
        </div>

        <p className="dev-mode-footnote">
          If a native launch fails, see <strong>docs/development/troubleshooting.md</strong>.
          The guide explains dependency mismatches, Python bridge errors, WebKitGTK, and
          Wayland protocol failures step by step.
        </p>
      </section>
    </main>
  );
}
