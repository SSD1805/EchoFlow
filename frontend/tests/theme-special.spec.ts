import { expect, test } from "@playwright/test";

const MONOCHROME_TOKENS = [
  "--bg",
  "--surface",
  "--surface-raised",
  "--surface-soft",
  "--ink",
  "--muted",
  "--border",
  "--accent",
  "--accent-strong",
  "--accent-soft",
  "--on-accent",
  "--focus",
  "--danger",
  "--control-bg",
  "--control-ink",
  "--control-border",
  "--selection-bg",
  "--selection-ink",
] as const;

function isGray(hex: string): boolean {
  const normalized = hex.trim().replace(/^#/, "");
  if (!/^[0-9a-f]{6}$/i.test(normalized)) return false;
  return normalized.slice(0, 2) === normalized.slice(2, 4) && normalized.slice(2, 4) === normalized.slice(4, 6);
}

test("Pride uses decoration without changing the semantic theme contract", async ({ page }) => {
  await page.goto("/?e2e=1");
  await page.getByLabel("Theme").selectOption("pride");

  const decoration = await page.evaluate(() =>
    getComputedStyle(document.body, "::before").backgroundImage,
  );
  expect(decoration).toContain("linear-gradient");
  await expect(page.locator("html")).toHaveCSS("color-scheme", /light/);
});

test("Monochrome semantic colors are genuinely grayscale", async ({ page }) => {
  await page.goto("/?e2e=1");
  await page.getByLabel("Theme").selectOption("monochrome");

  const tokens = await page.evaluate((names) => {
    const style = getComputedStyle(document.documentElement);
    return Object.fromEntries(names.map((name) => [name, style.getPropertyValue(name).trim()]));
  }, MONOCHROME_TOKENS);

  for (const name of MONOCHROME_TOKENS) {
    expect(isGray(tokens[name] ?? ""), `${name} should be grayscale`).toBe(true);
  }
  await expect(page.locator("html")).toHaveCSS("color-scheme", /dark/);
});
