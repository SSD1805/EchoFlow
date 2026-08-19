"""One-shot normalization of Mermaid blocks toward GitHub-portable syntax.

This script is intentionally mechanical. It never changes graph edges or labels. It only
normalizes the diagram declaration and removes renderer-specific styling directives that
EchoFlow's documentation contract says must not carry meaning.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FRONT_DOOR_FALLBACKS = {
    ROOT / "README.md": (
        "Text fallback: source media is inspected and transcribed locally into canonical "
        "JSON; rebuildable search finds passages; canonical verification turns results "
        "back into evidence; durable research state attaches human knowledge to that "
        "evidence; custody planning keeps deletion explicit."
    ),
    ROOT / "ROADMAP.md": (
        "Text fallback: EchoFlow progresses from local media through reliable local "
        "transcription, canonical evidence, retrieval, verified navigation, durable "
        "research, discovery, safe lifecycle controls, incremental refresh, desktop "
        "workflows, packaging, portability, and release qualification."
    ),
}

_DIRECTIONS = {"LR", "RL", "TD", "TB", "BT"}
_STYLE_PREFIXES = ("classDef ", "class ", "style ", "linkStyle ")


def _normalize_block(lines: list[str]) -> list[str]:
    normalized: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not normalized and stripped.startswith("flowchart "):
            parts = stripped.split()
            if len(parts) == 2 and parts[1] in _DIRECTIONS:
                indent = line[: len(line) - len(line.lstrip())]
                normalized.append(f"{indent}graph {parts[1]};")
                continue
        if stripped.startswith(_STYLE_PREFIXES):
            continue
        normalized.append(line)
    while normalized and not normalized[-1].strip():
        normalized.pop()
    return normalized


def _normalize_markdown(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines()
    output: list[str] = []
    in_mermaid = False
    block: list[str] = []
    first_block_closed_at: int | None = None

    for line in lines:
        if not in_mermaid and line == "```mermaid":
            in_mermaid = True
            block = []
            output.append(line)
            continue
        if in_mermaid and line == "```":
            output.extend(_normalize_block(block))
            output.append(line)
            in_mermaid = False
            if first_block_closed_at is None:
                first_block_closed_at = len(output)
            continue
        if in_mermaid:
            block.append(line)
        else:
            output.append(line)

    if in_mermaid:
        raise ValueError(f"unterminated Mermaid fence in {path.relative_to(ROOT)}")

    fallback = FRONT_DOOR_FALLBACKS.get(path)
    if fallback and first_block_closed_at is not None:
        tail = "\n".join(output[first_block_closed_at : first_block_closed_at + 20])
        if "Text fallback:" not in tail:
            output[first_block_closed_at:first_block_closed_at] = ["", fallback]

    updated = "\n".join(output) + "\n"
    if updated == original:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    changed: list[Path] = []
    candidates = [ROOT / "README.md", ROOT / "ROADMAP.md", *sorted((ROOT / "docs").rglob("*.md"))]
    for path in candidates:
        if _normalize_markdown(path):
            changed.append(path)
    for path in changed:
        print(path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
