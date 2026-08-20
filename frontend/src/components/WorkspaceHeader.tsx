import { THEMES, type Theme } from "../themes";

export type { Theme } from "../themes";

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
      <label className="theme-picker">
        <span>Theme</span>
        <select
          aria-label="Theme"
          value={theme}
          onChange={(event) => onThemeChange(event.target.value as Theme)}
        >
          {THEMES.map((option) => (
            <option key={option.id} value={option.id}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
    </header>
  );
}
