# Desktop themes and accessibility

EchoFlow themes are presentation, not application state. A theme may change color and visual tone; it may not change evidence, research, processing behavior, or what an interaction means.

## One semantic token contract

Every desktop skin supplies the same semantic CSS variables in `frontend/src/styles.css`:

| Token | Meaning |
|---|---|
| `--bg` | application background |
| `--surface`, `--surface-raised`, `--surface-soft` | content surfaces at increasing visual emphasis |
| `--ink`, `--muted` | primary and secondary text |
| `--border` | general structural boundary |
| `--accent`, `--accent-strong`, `--accent-soft`, `--on-accent` | interactive emphasis and its readable foreground |
| `--control-bg`, `--control-ink`, `--control-border` | native and custom form controls |
| `--focus` | keyboard focus indicator |
| `--danger` | destructive/error text |
| `--selection-bg`, `--selection-ink` | selected text |

Components consume those meanings. They do not own theme-specific grays, whites, blues, or dark-mode exceptions. If a component needs a new visual role, add a semantic token only when the role is genuinely distinct across the product.

The theme registry in `frontend/src/themes.ts` owns the supported IDs, display names, and light/dark browser scheme. CSS owns the palette values. That split prevents the theme menu, component code, and palette definitions from becoming three competing sources of truth.

## Current skins

EchoFlow ships six skins through one compact **Theme** picker:

- **Archive**: warm paper neutrals with restrained teal;
- **Midnight**: charcoal surfaces with cool teal;
- **Paper**: cool neutral paper with ink blue;
- **Moss**: soft mineral greens;
- **Plum**: muted aubergine on warm pale surfaces; and
- **Ember**: warm near-black surfaces with amber emphasis.

The set is intentionally varied by temperature and character without changing component semantics. Four light skins and two dark skins also exercise both browser `color-scheme` paths instead of treating dark mode as a one-off exception.

Theme choice is stored only in browser-local presentation preferences. Failure to read or write that preference falls back to Archive and must never block the evidence workspace.

## Contrast is a testable invariant

The Playwright theme matrix checks every skin against the same WCAG-oriented thresholds:

- ordinary text pairs: **4.5:1 or greater**;
- control boundaries and focus indicators: **3:1 or greater**;
- accent buttons use `--on-accent` rather than assuming white text; and
- text selection has its own foreground/background pair.

The current token set is deliberately above the minimums. In the checked pairs, the lowest text contrast is about **5.69:1** and the lowest non-text boundary/focus contrast is about **4.19:1**. Those margins are useful because real components can introduce antialiasing, opacity, and surrounding-color effects that make barely passing palettes brittle.

`frontend/tests/theme-accessibility.spec.ts` also verifies the declared browser `color-scheme`, exercises the real Research controls in every skin, and runs axe. The normal interaction suite continues to cover semantic roles and keyboard behavior.

## Native controls are part of the theme

Inputs, selects, textareas, checkboxes, radio buttons, options, placeholders, disabled states, text selection, and focus indicators are normalized centrally. Every theme explicitly declares `color-scheme`, so the browser and operating system do not have to guess whether a native control belongs to a light or dark surface.

Do not fix a contrast problem by adding a component-local `#666`, `#fff`, or platform-specific gray. Fix the semantic role or token. The same repair should make the control correct in Research, Processing, import, Library, and future surfaces.

Browser automation cannot fully prove how an opened native select menu is painted by every Windows/macOS/Linux desktop stack. Representative-device qualification therefore still includes visual and keyboard checks for opened native controls, high-contrast/forced-colors modes, display scaling, and platform focus treatment.

## Color cannot be the only signal

Status, errors, selection, processing readiness, current/older evidence, disabled actions, and destructive scope must remain understandable without color. Use text, semantic structure, icons where useful, and ARIA/state attributes as appropriate. A new skin must not require a new interpretation of the interface.

## Adding a skin

A new theme is acceptable only when it:

1. is registered once in `themes.ts`;
2. supplies the complete semantic token set in `styles.css`;
3. declares an explicit light or dark `color-scheme`;
4. passes the shared contrast matrix and axe checks;
5. does not add component-specific palette overrides; and
6. remains legible for focused, selected, disabled, error, and form-control states.

This is intentionally more restrictive than “the screenshot looks good.” The product should make unreadable UI difficult to commit.
