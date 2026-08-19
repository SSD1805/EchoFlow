"""Verify Mermaid documentation remains portable across GitHub and local previews.

GitHub renders Mermaid fenced Markdown, while IDE extensions may accept additional syntax
or styling. EchoFlow keeps diagrams inside a deliberately small Mermaid subset and requires
both text and checked-in SVG fallbacks on the repository's load-bearing documentation front
doors.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONT_DOOR_FALLBACKS = {
    ROOT / "README.md": (
        "![EchoFlow recording-to-evidence flow](docs/diagrams/recording-to-evidence.svg)",
        ROOT / "docs" / "diagrams" / "recording-to-evidence.svg",
    ),
    ROOT / "ROADMAP.md": (
        "![EchoFlow product roadmap](docs/diagrams/product-roadmap.svg)",
        ROOT / "docs" / "diagrams" / "product-roadmap.svg",
    ),
    ROOT / "docs" / "README.md": (
        "![EchoFlow family portrait](diagrams/docs-family-portrait.svg)",
        ROOT / "docs" / "diagrams" / "docs-family-portrait.svg",
    ),
    ROOT / "docs" / "architecture" / "README.md": (
        "![EchoFlow system architecture](../diagrams/system-architecture.svg)",
        ROOT / "docs" / "diagrams" / "system-architecture.svg",
    ),
}
FRONT_DOORS = frozenset(FRONT_DOOR_FALLBACKS)
MERMAID_BLOCK = re.compile(r"```mermaid\n(?P<body>.*?)\n```", re.DOTALL)
PORTABLE_START = re.compile(
    r"^(?:graph|flowchart)\s+(?:LR|RL|TD|TB|BT);?$|^sequenceDiagram$|^info$"
)
FORBIDDEN = (
    "classDef",
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


def _fallback_errors(path: Path, text: str) -> list[str]:
    fallback = FRONT_DOOR_FALLBACKS.get(path)
    if fallback is None:
        return []

    image_markdown, asset = fallback
    errors: list[str] = []
    if image_markdown not in text:
        errors.append("needs its checked-in SVG fallback before the Mermaid source")
    if not asset.is_file():
        errors.append(f"missing SVG fallback asset {asset.relative_to(ROOT)}")
    return errors


def _diagram_errors(path: Path, text: str, match: re.Match[str], index: int) -> list[str]:
    body = match.group("body")
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    errors: list[str] = []
    if not lines or not PORTABLE_START.fullmatch(lines[0]):
        errors.append(f"diagram {index} must start with portable graph/flowchart/sequence syntax")
    for token in FORBIDDEN:
        if token in body:
            errors.append(f"diagram {index} uses non-portable construct {token!r}")

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
    errors.extend(_fallback_errors(path, text))
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
        "Mermaid documentation is GitHub-portable; front doors have visible SVG and text fallbacks."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
