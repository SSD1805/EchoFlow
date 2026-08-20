# Post-MVP research roadmap 🔭

EchoFlow's first product milestone is intentionally narrower than its long-term possibility.
The MVP / pre-1.0 critical path is still: make a normal desktop application that can safely
process local recordings, preserve canonical evidence, search and annotate it, recover from
common failures, play verified source media, manage lifecycle, package cleanly, and move or
back up durable work.

Once that loop is coherent, EchoFlow can grow from a recorded-evidence workspace into a
broader **research provenance environment**. The capabilities below are second-horizon
features, not reasons to delay the first desktop release.

One proposed feature does **not** belong here: adaptive zero-knob execution. Machine
inspection, safe model/compute selection, resource estimates, graceful degradation, and an
explainable automatic choice belong in the first desktop Processing Center. A normal user
should not need to understand Whisper model sizing, accelerator topology, thread counts, or
memory headroom just to transcribe an interview.

## 1. Portable research bundle

Provide one explicit, verifiable package for moving an EchoFlow project between computers.
The bundle should contain durable authority and omit rebuildable machinery:

- canonical transcript evidence;
- authoritative SQLite human research state;
- speaker display labels and other durable user-authored metadata;
- a manifest with schema/application compatibility metadata and cryptographic hashes; and
- optionally source recordings when the user deliberately includes them.

DuckDB indexes, embedding caches, publication exports, temporary audio, and other derived
state should remain disposable and rebuildable. Import/restore must verify the manifest and
reconcile machine-local paths rather than silently trusting stale absolute locations.

## 2. Evidence packet exports

Export selected research to Markdown, DOCX, and PDF as a human-readable evidence packet.
Packets should be able to carry:

- source excerpts;
- notes, tags, and collections;
- speaker display labels alongside anonymous evidence refs where relevant;
- timestamps and numeric source-relative coordinates;
- document and canonical-generation identity;
- processing/source provenance appropriate to the export; and
- EchoFlow deep-links or durable locators back to verified evidence when the receiving
  environment supports them.

An evidence packet is a publication view, never a replacement for canonical transcript or
research authority.

## 3. REFI-QDA interoperability

Support the REFI-QDA exchange format so EchoFlow can participate in the wider qualitative
research ecosystem instead of recreating every mature QDA feature from NVivo, MAXQDA,
ATLAS.ti, QualCoder, and related tools.

Prefer export before import. Export establishes a safe interoperability boundary first;
import later needs explicit mapping rules for foreign source identities, coding structures,
annotations, speakers, timestamps, and any concepts that do not map losslessly onto
EchoFlow's evidence model.

External exchange formats must not become canonical transcript authority inside EchoFlow.

## 4. Saved-question snapshots and diffs

Saved searches are durable questions rather than frozen result lists. Preserve optional run
snapshots so a researcher can ask:

> I ran this question three months ago. What evidence is new, gone, or generation-shifted?

A deterministic comparison can classify evidence identities as added, removed, unchanged,
or changed across canonical generations. The UI should distinguish corpus growth from
transcript replacement and should never imply that a changed result means the underlying
real-world claim became true or false.

This is particularly useful for longitudinal interviews, recurring meetings, investigative
corpora, oral-history projects, and research collections that continue to grow.

## 5. Comparison and contradiction workspace

Let the user place two evidence sets, interviews, collections, speakers, or saved-question
results side by side. Align passages using explicit research relationships and inspectable
retrieval signals such as shared tags, collections, dates, lexical overlap, or qualified
semantic similarity.

The workspace may help a human find tension. It must not manufacture a conclusion such as
"Participant A contradicts Participant B." Interpretation remains human research work.

## 6. Evidence-linked writing

Allow researchers to build an outline, chapter, memo, article, or report from durable notes
while retaining the evidence relationships that motivated the writing.

A section or paragraph may cite one or more verified excerpts. Word/Markdown export should
preserve useful citations, footnotes/endnotes, deep-links, or an evidence appendix so the
trail from synthesis back to source remains inspectable after writing leaves EchoFlow.

The feature does not require generative writing. The researcher can author every word while
EchoFlow protects provenance.

## 7. Live research capture

Eventually support live recording sessions with a clearly provisional layer:

1. record local media;
2. show a provisional live transcript;
3. let the user create bookmarks, scratch notes, and tags during the session;
4. run normal final canonical processing after recording completes; and
5. reconcile provisional coordinates to verified canonical evidence.

Live ASR must never silently become canonical transcript authority. Reconciliation needs
explicit outcomes such as exact, adjusted, ambiguous, or unresolved. Human notes survive
regardless, while evidence anchors become canonical only when EchoFlow can establish the
relationship safely.

## Product guardrails for the second horizon

These features extend EchoFlow's research surface without weakening its custody model:

- provisional state never masquerades as canonical evidence;
- exports retain provenance and identify themselves as publications;
- interoperability does not promote a foreign project format above canonical evidence;
- comparisons expose evidence rather than fabricate interpretations;
- evidence-linked writing keeps a navigable trail back to source;
- portable bundles include durable authority and omit disposable indexes by default; and
- new automation remains local-first, inspectable, resource-aware, and optional where it
  changes acquisition, interpretation, or custody.

The long-term trajectory is therefore deliberate:

**local transcription → recorded-evidence workspace → research workspace → research
provenance environment.**
