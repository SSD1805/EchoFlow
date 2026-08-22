# Why Scholion?

**Scholion** is the product name. The technical identifier is `scholion`.

A *scholion* is an explanatory, critical, or interpretive note attached to a text; the plural is *scholia*. In manuscript traditions, scholia preserve human reading around a source without becoming the source itself.

That distinction matches Scholion's evidence model unusually well:

```text
recording
   ↓
canonical transcript evidence
   ↓
verified passage / exact source time
   ↓
human notes, labels, collections, and saved research questions
```

The original recording and canonical transcript remain evidence. Human research accumulates around verified evidence, can point back to it precisely, and remains durable user-owned knowledge. Search indexes, embeddings, presentation exports, and other projections can be rebuilt without becoming a second source of truth.

The name therefore describes the product's job rather than its implementation. Scholion is not merely a transcription engine. It is a private, local-first workspace for inspecting recorded evidence and building durable research around it.

## Canonical identity

Use these forms consistently:

| Surface | Identity |
|---|---|
| Product/display name | `Scholion` |
| Python package | `scholion` |
| CLI command | `scholion` |
| Environment prefix | `SCHOLION_` |
| Desktop package | `scholion-desktop` |
| Tauri product/window name | `Scholion` |
| Tauri identifier | `org.scholion.desktop` |
| Private playback protocol | `scholion-media` |

Repository hosting, installer/update identities, and release artifacts should use the same product identity when those surfaces are finalized. Identity changes must never silently move, delete, or invalidate authoritative user evidence.
