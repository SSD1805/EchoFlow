from __future__ import annotations

import hashlib
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DIAGRAMS = (
    ("README.md", "docs/diagrams/recording-to-evidence.svg"),
    ("ROADMAP.md", "docs/diagrams/product-roadmap.svg"),
    ("docs/README.md", "docs/diagrams/docs-family-portrait.svg"),
    ("docs/architecture/README.md", "docs/diagrams/system-architecture.svg"),
)
_MERMAID_BLOCK = re.compile(r"```mermaid\s*\n(?P<body>.*?)\n```", re.DOTALL)
_SVG_SOURCE_HASH = re.compile(r"sha256=(?P<digest>[0-9a-f]{64})")


def _first_mermaid_source(path: Path) -> str:
    match = _MERMAID_BLOCK.search(path.read_text(encoding="utf-8"))
    assert match is not None, f"{path.relative_to(_REPO_ROOT)} has no Mermaid source"
    return match.group("body").strip()


def _svg_source_hash(path: Path) -> str:
    match = _SVG_SOURCE_HASH.search(path.read_text(encoding="utf-8"))
    assert match is not None, f"{path.relative_to(_REPO_ROOT)} has no Mermaid source hash"
    return match.group("digest")


def test_high_traffic_diagram_fallbacks_match_mermaid_sources() -> None:
    for markdown_name, svg_name in _DIAGRAMS:
        markdown_path = _REPO_ROOT / markdown_name
        svg_path = _REPO_ROOT / svg_name
        source = _first_mermaid_source(markdown_path)
        expected = hashlib.sha256(source.encode("utf-8")).hexdigest()
        assert _svg_source_hash(svg_path) == expected, (
            f"{svg_name} is stale relative to {markdown_name}; regenerate the visible "
            "SVG fallback when changing its Mermaid source"
        )
