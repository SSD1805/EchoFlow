import { useEffect, useMemo, useState } from "react";

import { createDesktopClient } from "./api/desktop";
import { type Theme } from "./components/WorkspaceHeader";
import { IntakeWorkspace } from "./IntakeWorkspace";
import { SearchWorkspace } from "./SearchWorkspace";

const client = createDesktopClient();

type View = "intake" | "library";

export function App() {
  const [theme, setTheme] = useState<Theme>("archive");
  const [view, setView] = useState<View>("intake");

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const workspace = useMemo(
    () =>
      view === "intake" ? (
        <IntakeWorkspace client={client} theme={theme} onThemeChange={setTheme} />
      ) : (
        <SearchWorkspace client={client} theme={theme} onThemeChange={setTheme} />
      ),
    [theme, view],
  );

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
          <button
            className={view === "intake" ? "nav-item nav-item-active" : "nav-item"}
            type="button"
            aria-current={view === "intake" ? "page" : undefined}
            onClick={() => setView("intake")}
          >
            <span aria-hidden="true">＋</span> Add evidence
          </button>
          <button
            className={view === "library" ? "nav-item nav-item-active" : "nav-item"}
            type="button"
            aria-current={view === "library" ? "page" : undefined}
            onClick={() => setView("library")}
          >
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

      <main className="workspace">{workspace}</main>
    </div>
  );
}
