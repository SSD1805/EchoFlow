import { expect, test } from "@playwright/test";

import {
  nativeInvokeErrorMessage,
  parseNativeProtocolResponse,
} from "../src/api/nativeProtocol";
import { formatEvidenceTime } from "../src/format";
import { DEFAULT_THEME, isTheme, THEMES } from "../src/themes";

test("theme registry has one stable identifier and label per skin", () => {
  const ids = THEMES.map((theme) => theme.id);
  const labels = THEMES.map((theme) => theme.label);

  expect(new Set(ids).size).toBe(ids.length);
  expect(new Set(labels).size).toBe(labels.length);
  expect(ids).toEqual([
    "archive",
    "midnight",
    "paper",
    "moss",
    "plum",
    "ember",
    "pride",
    "monochrome",
  ]);
  expect(DEFAULT_THEME).toBe("archive");
});

test("theme validation accepts registered values and rejects lookalikes", () => {
  for (const theme of THEMES) {
    expect(isTheme(theme.id)).toBe(true);
    expect(["light", "dark"]).toContain(theme.scheme);
  }
  for (const invalid of [null, "", "Archive", "PRIDE", "dark", "unknown"] as const) {
    expect(isTheme(invalid)).toBe(false);
  }
});

test("evidence time formatting is deterministic at minute and hour boundaries", () => {
  expect(formatEvidenceTime(-10)).toBe("0:00");
  expect(formatEvidenceTime(0)).toBe("0:00");
  expect(formatEvidenceTime(59.999)).toBe("0:59");
  expect(formatEvidenceTime(60)).toBe("1:00");
  expect(formatEvidenceTime(3599.999)).toBe("59:59");
  expect(formatEvidenceTime(3600)).toBe("1:00:00");
  expect(formatEvidenceTime(3661.9)).toBe("1:01:01");
});

test("Pride and Monochrome advertise the correct native scheme", () => {
  expect(THEMES.find((theme) => theme.id === "pride")?.scheme).toBe("light");
  expect(THEMES.find((theme) => theme.id === "monochrome")?.scheme).toBe("dark");
});

test("native protocol parser accepts version one and rejects malformed envelopes", () => {
  const messages = {
    invalid: "invalid native response",
    incompatible: "incompatible native response",
    failure: "native request failed",
  } as const;

  expect(
    parseNativeProtocolResponse<{ value: number }>(
      {
        protocol_version: 1,
        request_id: "request-1",
        ok: true,
        result: { value: 7 },
        error: null,
      },
      messages,
    ),
  ).toEqual({
    protocol_version: 1,
    request_id: "request-1",
    ok: true,
    result: { value: 7 },
    error: null,
  });

  expect(() => parseNativeProtocolResponse(null, messages)).toThrow(
    "invalid native response",
  );
  expect(() =>
    parseNativeProtocolResponse(
      { protocol_version: 2, request_id: "request-1", ok: true },
      messages,
    ),
  ).toThrow("incompatible native response");
});

test("native invoke errors preserve controlled Rust messages", () => {
  expect(
    nativeInvokeErrorMessage(
      "Scholion's local Python service exited unexpectedly",
      "fallback",
    ),
  ).toBe("Scholion's local Python service exited unexpectedly");
  expect(nativeInvokeErrorMessage(new Error("native command failed"), "fallback")).toBe(
    "native command failed",
  );
  expect(nativeInvokeErrorMessage({ message: "structured native failure" }, "fallback")).toBe(
    "structured native failure",
  );
  expect(nativeInvokeErrorMessage({ code: "unknown" }, "fallback")).toBe("fallback");
});
