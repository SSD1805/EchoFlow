import { useEffect, useMemo, useState } from "react";

import { createDesktopClient } from "./api/desktop";
import { createPlaybackClient } from "./api/playback";
import { createProcessingClient } from "./api/processing";
import { createTranscriptToolsClient } from "./api/transcriptTools";
import { type Theme } from "./components/WorkspaceHeader";
import { IntakeWorkspace } from "./IntakeWorkspace";
import { PlaybackProvider } from "./PlaybackContext";
import { ProcessingCenter } from "./ProcessingCenter";
import { ResearchWorkspaceWithAnchorReview } from "./ResearchWorkspaceWithAnchorReview";
import { SearchWorkspace } from "./SearchWorkspace";
import { DEFAULT_THEME, isTheme, THEME_STORAGE_KEY } from "./themes";
import "./processing-center.css";
import "./theme-extras.css";

const client = createDesktopClient();
const playback = createPlaybackClient();
const processing = createProcessingClient();
const transcriptTools = createTranscriptToolsClient();

type View = "intake" | "processing" | "library" | "research";

function initialTheme(): Theme {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isTheme(stored) ? stored : DEFAULT_THEME;
  } catch {
    return DEFAULT_THEME;
  }
}

export function App() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [view, setView] = useState<View>("intake");

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      // Presentation preferences must never block the local evidence workspace.
    }
  }, [theme]);

  const workspace = useMemo(() => {
    if (view === "intake") {
      return (
        <IntakeWorkspace client={client} theme={theme} onThemeChange={setTheme} />
      );
    }
    if (view === "processing") {
      return (
        <ProcessingCenter
          client={client}
          processing={processing}
          theme={theme}
          onThemeChange={setTheme}
        />
      );
    }
    if (view === "library") {
      return (
        <SearchWorkspace
          client={client}
          transcriptTools={transcriptTools}
          theme={theme}
          onThemeChange={setTheme}
        />
      );
    }
    return (
      <ResearchWorkspaceWithAnchorReview
        client={client}
        theme={theme}
        onThemeChange={setTheme}
      />
    );
  }, [theme, view]);

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true">
            E
          </div>
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
            className={view === "processing" ? "nav-item nav-item-active" : "nav-item"}
            type="button"
            aria-current={view === "processing" ? "page" : undefined}
            onClick={() => setView("processing")}
          >
            <span aria-hidden="true">◉</span> Processing
          </button>
          <button
            className={view === "library" ? "nav-item nav-item-active" : "nav-item"}
            type="button"
            aria-current={view === "library" ? "page" : undefined}
            onClick={() => setView("library")}
          >
            <span aria-hidden="true">⌕</span> Library
          </button>
          <button
            className={view === "research" ? "nav-item nav-item-active" : "nav-item"}
            type="button"
            aria-current={view === "research" ? "page" : undefined}
            onClick={() => setView("research")}
          >
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

      <PlaybackProvider client={playback}>
        <main className="workspace">{workspace}</main>
      </PlaybackProvider>
    </div>
  );
}
