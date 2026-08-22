"""Verify Scholion Mermaid docs stay GitHub-friendly and visually intentional.

GitHub documents Mermaid fenced blocks directly and accepts the classic ``graph TD;``
form. Scholion also uses Mermaid's ``flowchart`` spelling. The verifier protects direct
visibility, simple portable structure, the established palette, and optional secondary
static fallbacks without rewriting one valid spelling into another.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONT_DOOR_FALLBACKS = {
    ROOT / "README.md": (
        "docs/diagrams/recording-to-evidence.svg",
        ROOT / "docs" / "diagrams" / "recording-to-evidence.svg",
    ),
    ROOT / "ROADMAP.md": (
        "docs/diagrams/product-roadmap.svg",
        ROOT / "docs" / "diagrams" / "product-roadmap.svg",
    ),
    ROOT / "docs" / "README.md": (
        "diagrams/docs-family-portrait.svg",
        ROOT / "docs" / "diagrams" / "docs-family-portrait.svg",
    ),
    ROOT / "docs" / "architecture" / "README.md": (
        "../diagrams/system-architecture.svg",
        ROOT / "docs" / "diagrams" / "system-architecture.svg",
    ),
}
FRONT_DOORS = frozenset(FRONT_DOOR_FALLBACKS)
MERMAID_BLOCK = re.compile(r"```mermaid\n(?P<body>.*?)\n```", re.DOTALL)
PORTABLE_START = re.compile(
    r"^(?:graph|flowchart)\s+(?:LR|RL|TD|TB|BT);?$|^sequenceDiagram$|^info$"
)
CLASSDEF = re.compile(
    r"^classDef\s+[A-Za-z][A-Za-z0-9_-]*\s+"
    r"fill:(#[0-9A-Fa-f]{6}),stroke:(#[0-9A-Fa-f]{6}),"
    r"stroke-width:2px,color:(#[0-9A-Fa-f]{6});?$"
)
FALLBACK_SHA = re.compile(r"<!-- mermaid-sha256: ([0-9a-f]{64}) -->")
DETAILS_OPEN = re.compile(r"(?m)^<details(?:\s[^>]*)?>\s*$")
DETAILS_CLOSE = re.compile(r"(?m)^</details>\s*$")
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
APPROVED_SVG_COLORS = frozenset(value for style in APPROVED_STYLES for value in style)
FORBIDDEN = ("linkStyle", "%%{", "<br", "<div", "<span")


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
                f"diagram {diagram_index} uses colors outside the Scholion Mermaid palette"
            )
    return errors


def _inside_details(text: str, offset: int) -> bool:
    """Return whether offset is inside an actual line-level HTML disclosure.

    Literal documentation prose such as ``<details>`` must not be mistaken for a real
    opening tag. Scholion's Markdown disclosures use standalone line-level tags.
    """

    before = text[:offset]
    return len(DETAILS_OPEN.findall(before)) > len(DETAILS_CLOSE.findall(before))


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
        tail = text[match.end() : match.end() + 1_500]
        if "Text fallback:" not in tail:
            errors.append(f"diagram {index} needs a nearby 'Text fallback:' paragraph")
    return errors


def _fallback_errors(path: Path, text: str, blocks: list[re.Match[str]]) -> list[str]:
    reference, svg_path = FRONT_DOOR_FALLBACKS[path]
    errors: list[str] = []
    if not blocks:
        return errors
    reference_offset = text.find(reference)
    if reference_offset < 0:
        errors.append("front-door diagram needs its secondary static SVG fallback")
        return errors
    if reference_offset < blocks[0].end():
        errors.append(
            "static SVG fallback must appear after the directly visible Mermaid"
        )
    if "Static diagram fallback" not in text[blocks[0].end() : reference_offset + 800]:
        errors.append("static SVG fallback needs a clear disclosure label")
    if not svg_path.is_file():
        errors.append(f"static SVG fallback is missing: {svg_path.relative_to(ROOT)}")
        return errors

    svg = svg_path.read_text(encoding="utf-8")
    if "currentColor" in svg:
        errors.append("static SVG fallback must use fixed colors, not currentColor")
    if "<title" not in svg or "<desc" not in svg:
        errors.append("static SVG fallback needs accessible <title> and <desc>")
    if not any(color in svg.upper() for color in APPROVED_SVG_COLORS):
        errors.append("static SVG fallback must use the approved Scholion palette")

    sha_match = FALLBACK_SHA.search(svg)
    expected = hashlib.sha256(blocks[0].group("body").encode("utf-8")).hexdigest()
    if sha_match is None or sha_match.group(1) != expected:
        errors.append("static SVG fallback is out of sync with its Mermaid source")
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
    if path in FRONT_DOORS:
        errors.extend(_fallback_errors(path, text, blocks))
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
        "preserves the Scholion palette, and keeps secondary SVG fallbacks synchronized."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
