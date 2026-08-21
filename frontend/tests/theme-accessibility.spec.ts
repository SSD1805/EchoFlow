import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { THEMES } from "../src/themes";

type Rgb = [number, number, number];

function parseHex(value: string): Rgb {
  const hex = value.trim().replace(/^#/, "");
  if (!/^[0-9a-f]{6}$/i.test(hex)) throw new Error(`Expected six-digit hex color, got ${value}`);
  return [
    Number.parseInt(hex.slice(0, 2), 16),
    Number.parseInt(hex.slice(2, 4), 16),
    Number.parseInt(hex.slice(4, 6), 16),
  ];
}

function normalizeChannel(channel: number): number {
  const value = channel / 255;
  return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
}

function luminance([red, green, blue]: Rgb): number {
  return (
    0.2126 * normalizeChannel(red) +
    0.7152 * normalizeChannel(green) +
    0.0722 * normalizeChannel(blue)
  );
}

function contrast(left: string, right: string): number {
  const a = luminance(parseHex(left));
  const b = luminance(parseHex(right));
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

function token(tokens: Record<string, string>, name: string): string {
  const value = tokens[name];
  if (!value) throw new Error(`Missing required semantic theme token: ${name}`);
  return value;
}

const TEXT_PAIRS = [
  ["--ink", "--bg"],
  ["--muted", "--bg"],
  ["--ink", "--surface"],
  ["--muted", "--surface"],
  ["--accent-strong", "--surface"],
  ["--on-accent", "--accent"],
  ["--control-ink", "--control-bg"],
  ["--danger", "--surface-raised"],
  ["--selection-ink", "--selection-bg"],
] as const;

const NON_TEXT_PAIRS = [
  ["--control-border", "--control-bg"],
  ["--focus", "--surface-raised"],
] as const;

for (const theme of THEMES) {
  test(`${theme.label} theme qualifies text, controls, native scheme, and Research a11y`, async ({ page }) => {
    await page.goto("/?e2e=1");
    await page.getByLabel("Theme").selectOption(theme.id);
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme.id);

    const snapshot = await page.evaluate(() => {
      const style = getComputedStyle(document.documentElement);
      const names = [
        "--bg",
        "--surface",
        "--surface-raised",
        "--ink",
        "--muted",
        "--accent",
        "--accent-strong",
        "--on-accent",
        "--focus",
        "--danger",
        "--control-bg",
        "--control-ink",
        "--control-border",
        "--selection-bg",
        "--selection-ink",
      ];
      return {
        colorScheme: style.colorScheme,
        tokens: Object.fromEntries(names.map((name) => [name, style.getPropertyValue(name).trim()])),
      };
    });

    expect(snapshot.colorScheme).toContain(theme.scheme);
    for (const [foreground, background] of TEXT_PAIRS) {
      expect(
        contrast(token(snapshot.tokens, foreground), token(snapshot.tokens, background)),
        `${theme.label}: ${foreground} on ${background}`,
      ).toBeGreaterThanOrEqual(4.5);
    }
    for (const [foreground, background] of NON_TEXT_PAIRS) {
      expect(
        contrast(token(snapshot.tokens, foreground), token(snapshot.tokens, background)),
        `${theme.label}: ${foreground} on ${background}`,
      ).toBeGreaterThanOrEqual(3);
    }

    await page.getByRole("button", { name: "Research" }).click();
    const panel = page.getByRole("region", { name: "What are you looking for?" });
    await panel.getByText("Search options", { exact: true }).click();
    const select = panel.getByLabel("Search by");
    await expect(select).toBeVisible();
    const controlStyle = await select.evaluate((element) => {
      const style = getComputedStyle(element);
      return { color: style.color, backgroundColor: style.backgroundColor };
    });
    expect(controlStyle.color).not.toBe(controlStyle.backgroundColor);

    const accessibility = await new AxeBuilder({ page }).analyze();
    expect(accessibility.violations).toEqual([]);
  });
}

test("theme picker is compact, complete, and persists locally", async ({ page }) => {
  await page.goto("/?e2e=1");

  const picker = page.getByLabel("Theme");
  await expect(picker.locator("option")).toHaveCount(THEMES.length);
  await expect(page.getByRole("button", { name: "Archive" })).toHaveCount(0);
  await picker.selectOption("monochrome");
  await page.reload();

  await expect(page.locator("html")).toHaveAttribute("data-theme", "monochrome");
  await expect(page.getByLabel("Theme")).toHaveValue("monochrome");
});
