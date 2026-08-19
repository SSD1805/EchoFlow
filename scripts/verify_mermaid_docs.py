"""Verify Mermaid documentation remains portable across GitHub and local previews.

GitHub renders Mermaid fenced Markdown, while IDE extensions may accept additional syntax
or styling. EchoFlow keeps diagrams inside a deliberately small Mermaid subset and requires
text fallbacks on the repository's load-bearing documentation front doors.
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
        body = match.group("body")
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        if not lines or not PORTABLE_START.fullmatch(lines[0]):
            errors.append(
                f"diagram {index} must start with portable graph/flowchart/sequence syntax"
            )
        for token in FORBIDDEN:
            if token in body:
                errors.append(f"diagram {index} uses non-portable construct {token!r}")

        if path in FRONT_DOORS:
            tail = text[match.end() : match.end() + 1_200]
            if "Text fallback:" not in tail:
                errors.append(f"diagram {index} needs a nearby 'Text fallback:' paragraph")

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

    print("Mermaid documentation is GitHub-portable; front doors have text fallbacks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
