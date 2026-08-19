export type Theme = "archive" | "midnight";

interface WorkspaceHeaderProps {
  eyebrow: string;
  title: string;
  theme: Theme;
  onThemeChange: (theme: Theme) => void;
}

export function WorkspaceHeader({
  eyebrow,
  title,
  theme,
  onThemeChange,
}: WorkspaceHeaderProps) {
  return (
    <header className="topbar">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
      </div>
      <div className="theme-switch" role="group" aria-label="Appearance">
        <button
          type="button"
          className={theme === "archive" ? "theme-active" : ""}
          aria-pressed={theme === "archive"}
          onClick={() => onThemeChange("archive")}
        >
          Archive
        </button>
        <button
          type="button"
          className={theme === "midnight" ? "theme-active" : ""}
          aria-pressed={theme === "midnight"}
          onClick={() => onThemeChange("midnight")}
        >
          Midnight
        </button>
      </div>
    </header>
  );
}
