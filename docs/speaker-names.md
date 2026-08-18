# Give the anonymous speakers names 👥✨

Diarization gives EchoFlow useful but intentionally anonymous evidence:

```text
speaker-01
speaker-02
speaker-03
```

That is excellent for provenance and terrible for remembering which person was Dr. Chen.

EchoFlow therefore keeps **two different facts** instead of pretending they are the same thing:

- `speaker-02` is machine-produced diarization evidence;
- `Dr. Chen` is a name **you** assigned to that anonymous speaker in this transcript generation.

The friendly label never rewrites the evidence underneath it.

```mermaid
flowchart LR
    D[Anonymous diarization evidence] --> R[speaker-02]
    R --> C[Canonical transcript coordinates]
    R --> U[User-authored display label]
    U --> V[Dr. Chen (speaker-02)]

    classDef evidence fill:#FFF0B8,stroke:#8A6B18,stroke-width:2px,color:#2C260F
    classDef user fill:#F9D5E5,stroke:#7B2E52,stroke-width:2px,color:#22151B
    classDef view fill:#DDF5E3,stroke:#347A46,stroke-width:2px,color:#142719

    class D,R,C evidence
    class U user
    class V view
```

🦝 **The raccoon may rebuild the search index. The raccoon may not eat your names.**

## Naming a speaker

First make sure the transcript is present in the local library, then inspect its anonymous speaker refs:

```bash
echoflow library speakers list TRANSCRIPT_ID
```

Assign a human-readable display label:

```bash
echoflow library speakers name TRANSCRIPT_ID speaker-02 "Dr. Chen"
```

EchoFlow will continue to retain `speaker-02` as the evidence reference and can present the friendly form as:

```text
Dr. Chen (speaker-02)
```

If you change your mind:

```bash
echoflow library speakers forget-name TRANSCRIPT_ID speaker-02
```

Every command also supports `--json` for machine-readable output.

## Why not just replace `speaker-02` with the name?

Because those statements come from different authorities.

Diarization says:

> this voice cluster received the recording-scoped anonymous reference `speaker-02`.

You say:

> I know this person is Dr. Chen, so show me that name while I work.

If EchoFlow overwrote one with the other, it would destroy the distinction between **derived evidence** and **human knowledge**. That distinction matters for reproducibility, correction, auditing, and future annotations.

## What if the transcript changes?

Speaker numbering is meaningful only inside the canonical transcript generation that produced it.

A re-transcription could change where speaker boundaries fall. It could even make tomorrow's `speaker-02` represent somebody different from today's `speaker-02`.

So a display label is bound to:

```text
transcript ID
+ exact canonical transcript SHA-256
+ anonymous speaker ref
```

If the canonical transcript changes, EchoFlow **keeps the old user-authored label** but refuses to silently apply it to the new generation.

```mermaid
flowchart TD
    A[Canonical transcript generation A] --> B[speaker-02]
    B --> C[User label: Dr. Chen]
    A -->|transcript changes| D[Canonical transcript generation B]
    D --> E[speaker-02]
    C -. retained but stale .-> F[User-authored state]
    C -. not silently reused .-> E

    classDef old fill:#FFF0B8,stroke:#8A6B18,stroke-width:2px,color:#2C260F
    classDef current fill:#D8EEFF,stroke:#2E617B,stroke-width:2px,color:#12222A
    classDef user fill:#F9D5E5,stroke:#7B2E52,stroke-width:2px,color:#22151B

    class A,B old
    class D,E current
    class C,F user
```

That is slightly fussy on purpose. EchoFlow would rather ask you to confirm a name than confidently attach Dr. Chen to the wrong human.

## What about speaker handoffs inside one transcript segment?

Word-level timing matters here.

A mixed ASR segment may have no single segment-level `speaker_ref` because the speaker changes halfway through. Its individual aligned words can still carry `speaker-01` and `speaker-02` evidence.

The speaker-label service inspects **both segment-level and aligned-word speaker evidence**, so those speakers remain available to name even when the enclosing sentence cannot honestly be assigned to one person.

💃 Finer evidence, less lying. A useful trade.

## Reading handoffs and overlap without flattening them

A speaker name is only useful if EchoFlow can show it where the evidence actually belongs.

The derived speaker transcript view combines canonical word timing with the preserved speaker-turn timeline:

```bash
echoflow library speakers transcript TRANSCRIPT_ID
```

A clean handoff can become two readable spans:

```text
00:00:04.100  Interviewer (speaker-01)       single-speaker  What happened next?
00:00:05.900  Dr. Chen (speaker-02)          single-speaker  We moved the samples.
```

If two diarized speakers are simultaneously active over the same aligned word interval, EchoFlow does not choose a winner:

```text
00:00:12.200  Interviewer (speaker-01)
              + Dr. Chen (speaker-02)         overlap         Sorry—
```

And if a coarse segment contains more than one speaker but lacks word timing precise enough to assign its text, the view says `mixed-unresolved` rather than pretending the whole sentence belongs to either person.

```mermaid
flowchart LR
    W[Canonical word timing] --> P[Derived speaker presentation]
    T[Speaker-turn timeline] --> P
    N[Your display labels] --> P
    P --> S[single-speaker]
    P --> O[overlap]
    P --> M[mixed-unresolved]
    P --> U[unattributed]

    classDef evidence fill:#FFF0B8,stroke:#8A6B18,stroke-width:2px,color:#2C260F
    classDef user fill:#F9D5E5,stroke:#7B2E52,stroke-width:2px,color:#22151B
    classDef view fill:#DDF5E3,stroke:#347A46,stroke-width:2px,color:#142719

    class W,T evidence
    class N user
    class P,S,O,M,U view
```

This view is **derived presentation**, not a new canonical transcript. Numeric source-relative seconds and the original anonymous refs remain visible in JSON, along with the canonical transcript SHA-256 that the view came from.

One conservative rule matters: if a canonical aligned word is unattributed, the presentation layer will not promote it to a single named speaker merely because one diarization turn happens to overlap. Presentation may expose additional **multi-speaker overlap**, but it does not manufacture a stronger single-speaker claim than canonical evidence already made.

## Do the names show up when I search too?

Yes. Ordinary transcript-library search now consumes the same current display-label state.

If you assigned:

```text
speaker-02 → Dr. Chen
```

then a human search result involving that speaker can show:

```text
Dr. Chen (speaker-02)
```

Machine-readable output keeps `speaker-02` in `speaker_refs` and exposes the friendly label separately. Ranking and speaker filters still operate on anonymous evidence refs. A human name is presentation, not a new search identity.

The search navigation layer resolves names only for the exact canonical generation behind the result. It also batches the lookup per transcript generation rather than repeatedly rereading private label state for every result row.

See **[From search result to the exact evidence](evidence-navigation.md)** for highlighting, context, and source seek behavior.

## Where are these labels stored?

Speaker names are **private user-authored state**, not rebuildable search state.

They live under EchoFlow's private application state, separate from:

- the canonical transcript;
- the lexical DuckDB index;
- semantic chunks and vectors; and
- checkpoint/recovery machinery.

Writes use EchoFlow's existing atomic private-file boundary.

This means rebuilding lexical or semantic search must not erase the names you assigned.

## What this does not do

Speaker display labels are not biometric identification. EchoFlow does not infer that `speaker-01` in two different recordings is the same person, and it does not search for somebody's identity from their voice.

Overlap-aware presentation also does not perform source separation. It represents simultaneous speaker evidence honestly using the timeline EchoFlow already has. Separating overlapping audio into estimated sources remains a later and materially heavier capability with its own compute, model-custody, and provenance requirements.

For the underlying diarization evidence model, security gate, and overlap rules, see **[Anonymous speaker diarization](architecture/diarization.md)**.
