# Anonymous speaker diarization 👥

EchoFlow treats diarization as **speaker-timeline evidence**, not identity.

In ordinary language: diarization tries to answer **who spoke when inside this one
recording?** It gives recording-scoped labels such as `speaker-01` and `speaker-02` so a
transcript can say which anonymous voice most likely owns a passage.

It does **not** mean “identify this human,” and EchoFlow does not infer that
`speaker-01` in one recording is the same person as `speaker-01` in another.

```mermaid
flowchart LR
    A[Recording audio] --> D[Local diarization]
    D --> T[Speaker-turn timeline]
    T --> P[Conservative projection onto transcript]
    P --> C[Canonical transcript evidence]

    classDef source fill:#F9D5E5,stroke:#7B2E52,stroke-width:2px,color:#22151B
    classDef process fill:#E8D9FF,stroke:#68469B,stroke-width:2px,color:#1F1630
    classDef evidence fill:#FFF0B8,stroke:#8A6B18,stroke-width:2px,color:#2C260F

    class A source
    class D,P process
    class T,C evidence
```

## What the user would see

The intended CLI surface is opt-in:

```bash
uv run echoflow transcribe interview.wav --diarize
```

If the speaker count is known:

```bash
uv run echoflow transcribe focus-group.wav --diarize --speakers 4
```

Or provide a bounded range:

```bash
uv run echoflow transcribe meeting.wav --diarize --min-speakers 2 --max-speakers 6
```

Exact and bounded speaker-count options are mutually exclusive. Speaker-count options
are invalid without `--diarize`.

## Current operational status: integrated, but security-held 🔐

The first adapter targets the open-source pyannote `community-1` pipeline.

As of August 2026, pyannote 4.0.7 requires Lightning and the current lock resolves
Lightning 2.6.5. That release is affected by CVE-2026-58659 / PYSEC-2026-3624, a
checkpoint-loading remote-code-execution vulnerability.

This is not an irrelevant transitive advisory. Pyannote subclasses
`lightning.LightningModule` and loads pretrained checkpoints through Lightning, so the
vulnerable path intersects the feature EchoFlow would actually execute.

EchoFlow therefore **fails closed** before pyannote import or model acquisition when the
installed Lightning safety cannot be established.

The dependency audit carries one narrow documented exception for that exact advisory
while the runtime compensating control remains in place. Other advisories still fail the
audit.

Once a compatible patched Lightning release is available and qualified, both the audit
exception and runtime hold should be removed.

So the current product description is deliberately precise:

> **Diarization is integrated, tested at the application boundary, and security-gated;
> it is not currently an operationally qualified everyday feature.**

## Privacy and model-acquisition boundary

Pyannote model acquisition may require accepting upstream model conditions and
authenticating with Hugging Face.

EchoFlow does not store a Hugging Face token in its own configuration.

Any model download authorization is narrowly scoped to diarization:

```bash
uv run echoflow transcribe interview.wav \
  --diarize \
  --allow-diarization-model-download
```

That flag does **not** authorize faster-whisper model downloads. ASR model acquisition
remains the separate explicit `echoflow models install MODEL` path.

Pyannote telemetry is disabled by EchoFlow before package import. Diarization provenance
records `telemetry_enabled: false`. Recording audio remains local during inference.

Once a snapshot is resolved into EchoFlow's configured private model cache, inference
uses the local snapshot path.

## Dependency footprint

Diarization is intentionally a separate dependency extra because pyannote brings a
large PyTorch-based stack:

```bash
uv sync --locked --extra transcription --extra diarization
```

Representative CPU-only Windows/Linux/macOS installation size, peak RAM, and sustained
real-time factor still need physical-device qualification before EchoFlow should call
this a comfortable feature for an 8 GB machine.

## The evidence model

The primary diarization artifact is a source-relative speaker-turn timeline:

```text
00:00.0 ─ 00:12.4  speaker-01
00:12.4 ─ 00:18.8  speaker-02
00:18.1 ─ 00:20.0  speaker-01   # overlap can exist
```

Overlap is real evidence, not an error condition.

Raw backend labels are not stable API. EchoFlow sorts turns deterministically and maps
them to `speaker-01`, `speaker-02`, and so on in first-seen timeline order.

The current canonical transcript schema keeps optional diarization fields in the same
structural contract rather than inventing a new schema version for each combination of
features.

## Why EchoFlow is conservative about putting a speaker name on text

ASR and diarization still come from independent evidence streams. Word-level timing
simply gives EchoFlow finer coordinates for reconciling them.

When native word timing exists, EchoFlow compares **each word interval** with the
speaker-turn timeline:

```text
word overlaps speaker-01 only
    → word.speaker_ref = speaker-01

word overlaps speaker-01 + speaker-02
    → word.speaker_ref = null

all words in one ASR segment resolve to speaker-01
    → segment.speaker_ref = speaker-01

words in one ASR segment resolve to speaker-01 → speaker-02
    → segment.speaker_ref = null
```

If word evidence is absent, EchoFlow preserves the older conservative whole-segment
rule: the segment gets a speaker only when exactly one unique diarized speaker overlaps
that segment.

The exact speaker-turn timeline is preserved either way.

That refusal matters. It is better to preserve “we know these voices overlap here” than
to confidently put the wrong speaker label in front of a sentence.

See [word-level timestamp alignment](word-alignment.md) for the timing, checkpoint, and
source-relative assembly contract.

## What alignment now unlocks ✨

Word timing lets EchoFlow stop treating a long ASR segment as the smallest practical
text coordinate.

The first payoff is already structural: a speaker handoff can be represented inside one
recognized segment without assigning the entire segment to either person.

The same evidence seam can later support:

- precise transcript highlighting;
- more exact jump-to-audio behavior;
- durable annotations anchored to smaller evidence spans;
- clearer overlap presentation; and
- cleaner future speaker-label UX.

Alignment does **not** solve simultaneous speech. If two active speakers overlap the same
word interval, the word remains unattributed. Later source separation may provide more
evidence, but EchoFlow does not manufacture certainty in the meantime.

## User-assigned display labels without biometric identity

A useful future feature is allowing the user to say:

```text
speaker-01 → Dr. Chen
speaker-02 → Interviewer
```

The important design rule is that this should be **display/user-authored state**, not a
rewrite of the underlying anonymous diarization evidence.

Conceptually:

```mermaid
flowchart LR
    A[speaker-01 evidence] --> B[User-authored display label: Dr. Chen]
    A --> C[Canonical speaker-turn coordinates]

    classDef evidence fill:#FFF0B8,stroke:#8A6B18,stroke-width:2px,color:#2C260F
    classDef user fill:#F9D5E5,stroke:#7B2E52,stroke-width:2px,color:#22151B

    class A,C evidence
    class B user
```

The label is meaningful user knowledge and must **not** share the deletion semantics of
a rebuildable search index.

EchoFlow can remain anonymous-by-default while still letting a researcher make their own
recording understandable.

## Better overlap handling before source separation

Overlap still deserves two distinct product steps.

First, EchoFlow improves **representation and presentation** using finer word timing,
explicit multi-speaker turn evidence, and UI/export behavior that does not force one
speaker when multiple voices are active.

Only later should EchoFlow consider **speech/source separation**, where the audio itself
is decomposed into estimated sources before or during recognition.

Source separation is materially heavier. It adds compute, model/dependency custody,
quality uncertainty, and new provenance questions. It should be justified by real
recordings after the simpler evidence model is strong.

🧜‍♀️ Deep technical water is permitted. Inventing confidence is not.

## Canonical and derived output behavior

When every aligned word in a segment resolves to one anonymous speaker, the segment can
retain that same `speaker_ref` as a convenience label and derived TXT/SRT/WebVTT views
may prefix it.

Mixed or ambiguous segments remain unlabeled at the segment level even when some words
have useful speaker evidence. Export rendering never changes timestamps or becomes
canonical custody.

Future user-assigned display labels should remain a presentation layer over stable
anonymous speaker references and durable transcript coordinates.

## Qualification boundary

The deterministic test surface covers:

- adapter/cache-only versus download policy;
- telemetry-disable behavior;
- deterministic label normalization;
- canonical schema integration;
- executor integration;
- conservative word/segment speaker projection;
- mixed-speaker handoffs and ambiguous word overlap;
- derived exports; and
- the fail-closed Lightning security gate.

The locked diarization dependency graph remains in normal/scheduled vulnerability
auditing.

A clean-wheel distribution lane imports the real pyannote/PyTorch runtime without
executing the gated model. A dedicated real-model acceptance workflow exists but remains
blocked by the dependency security gate; once unblocked, it is manual and
credential-gated rather than ordinary PR CI.

## Current deliberate limits

This capability does not currently provide:

- biometric speaker identification;
- cross-recording speaker linking;
- user-assigned display labels;
- a guarantee that engine word timing or diarization is always correct;
- polished overlap presentation;
- simultaneous-speaker/source separation; or
- a claim that the dependency footprint is suitable for every low-memory device.

The stable rule is:

> **Preserve speaker evidence first. Add convenience only when it does not fabricate
> certainty.**