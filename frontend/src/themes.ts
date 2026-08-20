export const THEMES = [
  { id: "archive", label: "Archive", scheme: "light" },
  { id: "midnight", label: "Midnight", scheme: "dark" },
  { id: "paper", label: "Paper", scheme: "light" },
  { id: "moss", label: "Moss", scheme: "light" },
  { id: "plum", label: "Plum", scheme: "light" },
  { id: "ember", label: "Ember", scheme: "dark" },
] as const;

export type Theme = (typeof THEMES)[number]["id"];

export const DEFAULT_THEME: Theme = "archive";
export const THEME_STORAGE_KEY = "echoflow.theme.v1";

export function isTheme(value: string | null): value is Theme {
  return value !== null && THEMES.some((theme) => theme.id === value);
}
