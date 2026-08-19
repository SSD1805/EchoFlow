"""Verify EchoFlow Mermaid docs stay GitHub-friendly and visually intentional.

The repository once had working, styled ``flowchart`` diagrams. A later normalization
rewrote them to ``graph ...;`` and stripped their class definitions, so this check protects
the known-good dialect instead of trying to reduce Mermaid to monochrome boxes.

Color is presentation, never the only carrier of meaning. Diagram labels and edges must
remain understandable without it, while approved class styles keep the documentation
visually consistent with EchoFlow's established palette.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONT_DOORS = frozenset(
    {
        ROOT / "README.md",
        ROOT / "ROADMAP.md",
        ROOT / "docs" / "README.md",
        ROOT / "docs" / "architecture" / "README.md",
    }
)
MERMAID_BLOCK = re.compile(r"```mermaid\n(?P<body>.*?)\n```", re.DOTALL)
PORTABLE_START = re.compile(
    r"^flowchart\s+(?:LR|RL|TD|TB|BT)$|^sequenceDiagram$|^info$"
)
CLASSDEF = re.compile(
    r"^classDef\s+[A-Za-z][A-Za-z0-9_-]*\s+"
    r"fill:(#[0-9A-Fa-f]{6}),stroke:(#[0-9A-Fa-f]{6}),"
    r"stroke-width:2px,color:(#[0-9A-Fa-f]{6})$"
)
APPROVED_STYLES = frozenset(
    {
        ("#D8EEFF", "#2E617B", "#12222A"),  # inspect / information
        ("#E8D9FF", "#68469B", "#1F1630"),  # process / decision
        ("#DDF5E3", "#347A46", "#142719"),  # success / derived view
        ("#FFF0B8", "#8A6B18", "#2C260F"),  # evidence / attention
        ("#F9D5E5", "#7B2E52", "#22151B"),  # source / human-authored
        ("#FFD6D6", "#9E3434", "#351616"),  # refusal / destructive state
    }
)
FORBIDDEN = (
    "linkStyle",
    "%%{",
    "<br",
    "<div",
    "<span",
)


def _markdown_files() -> tuple[Path, ...]:
    return (
        ROOT / "README.md",
        ROOT / "ROADMAP.md",
        *sorted((ROOT / "docs").rglob("*.md")),
    )


def _classdef_errors(body: str, diagram_index: int) -> list[str]:
    errors: list[str] = []
    for line in (line.strip() for line in body.splitlines()):
        if not line.startswith("classDef "):
            continue
        match = CLASSDEF.fullmatch(line)
        if match is None:
            errors.append(
                f"diagram {diagram_index} has a classDef outside the approved simple syntax"
            )
            continue
        style = tuple(value.upper() for value in match.groups())
        if style not in APPROVED_STYLES:
            errors.append(
                f"diagram {diagram_index} uses colors outside the EchoFlow Mermaid palette"
            )
    return errors


def _diagram_errors(
    path: Path, text: str, match: re.Match[str], index: int
) -> list[str]:
    body = match.group("body")
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    errors: list[str] = []
    if not lines or not PORTABLE_START.fullmatch(lines[0]):
        errors.append(
            f"diagram {index} must start with the known-good flowchart/sequence syntax"
        )
    for token in FORBIDDEN:
        if token in body:
            errors.append(f"diagram {index} uses non-portable construct {token!r}")
    errors.extend(_classdef_errors(body, index))

    if path in FRONT_DOORS:
        tail = text[match.end() : match.end() + 1_200]
        if "Text fallback:" not in tail:
            errors.append(f"diagram {index} needs a nearby 'Text fallback:' paragraph")
    return errors


def _errors_for(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    blocks = list(MERMAID_BLOCK.finditer(text))
    errors: list[str] = []

    exact_openings = sum(line == "```mermaid" for line in text.splitlines())
    if exact_openings != len(blocks):
        errors.append("contains an unterminated or malformed Mermaid fence")
    if "```mermaid " in text or "``` mermaid" in text:
        errors.append("Mermaid fences must be exactly ```mermaid")

    for index, match in enumerate(blocks, start=1):
        errors.extend(_diagram_errors(path, text, match, index))
    return errors


def main() -> int:
    failures: list[str] = []
    for path in _markdown_files():
        if not path.is_file():
            failures.append(f"missing documentation: {path.relative_to(ROOT)}")
            continue
        failures.extend(
            f"{path.relative_to(ROOT)}: {message}" for message in _errors_for(path)
        )

    if failures:
        print("Mermaid documentation portability check failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(
        "Mermaid documentation uses the known-good flowchart dialect; "
        "approved styling and front-door text fallbacks are intact."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
