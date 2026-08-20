"""Verify EchoFlow Mermaid docs stay GitHub-friendly and visually intentional.

GitHub documents Mermaid fenced blocks directly and accepts the classic ``graph TD;``
form. EchoFlow also uses Mermaid's ``flowchart`` spelling. The verifier therefore protects
visibility, simple portable structure, and the established palette rather than rewriting
one valid spelling into another.

A previous regression stripped class styles and later placed hand-maintained SVG fallbacks
above Mermaid blocks while collapsing the actual Mermaid inside ``<details>``. This check
prevents those presentation regressions from becoming the new contract.
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
DEPRECATED_FALLBACK_REFERENCES = {
    ROOT / "README.md": "docs/diagrams/recording-to-evidence.svg",
    ROOT / "ROADMAP.md": "docs/diagrams/product-roadmap.svg",
    ROOT / "docs" / "README.md": "diagrams/docs-family-portrait.svg",
    ROOT / "docs" / "architecture" / "README.md": "../diagrams/system-architecture.svg",
}
MERMAID_BLOCK = re.compile(r"```mermaid\n(?P<body>.*?)\n```", re.DOTALL)
PORTABLE_START = re.compile(
    r"^(?:graph|flowchart)\s+(?:LR|RL|TD|TB|BT);?$|^sequenceDiagram$|^info$"
)
DETAILS_OPEN = re.compile(r"^\s*<details(?:\s[^>]*)?>\s*$", re.MULTILINE)
DETAILS_CLOSE = re.compile(r"^\s*</details>\s*$", re.MULTILINE)
CLASSDEF = re.compile(
    r"^classDef\s+[A-Za-z][A-Za-z0-9_-]*\s+"
    r"fill:(#[0-9A-Fa-f]{6}),stroke:(#[0-9A-Fa-f]{6}),"
    r"stroke-width:2px,color:(#[0-9A-Fa-f]{6});?$"
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


def _inside_details(text: str, offset: int) -> bool:
    before = text[:offset]
    opens = [match.start() for match in DETAILS_OPEN.finditer(before)]
    if not opens:
        return False
    closes = [match.start() for match in DETAILS_CLOSE.finditer(before)]
    return not closes or opens[-1] > closes[-1]


def _diagram_errors(
    path: Path, text: str, match: re.Match[str], index: int
) -> list[str]:
    body = match.group("body")
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    errors: list[str] = []
    if not lines or not PORTABLE_START.fullmatch(lines[0]):
        errors.append(
            f"diagram {index} must start with portable graph/flowchart/sequence syntax"
        )
    if _inside_details(text, match.start()):
        errors.append(
            f"diagram {index} must be directly visible, not nested in <details>"
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

    deprecated = DEPRECATED_FALLBACK_REFERENCES.get(path)
    if deprecated is not None and deprecated in text:
        errors.append(
            "must not restore the hand-maintained SVG fallback in front of the Mermaid"
        )

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
        "Mermaid documentation is directly visible, uses portable graph/flowchart syntax, "
        "and preserves the approved EchoFlow palette."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
