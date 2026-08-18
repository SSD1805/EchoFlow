# Getting started with EchoFlow 💃

This is the **use-the-thing** guide.

You do not need to understand the architecture to follow it. EchoFlow will make several
technical decisions for you, including what resources are safely available, which local
transcription strategy fits, where private working state belongs, and how completed work
can be resumed or searched later.

If you want the tour first, visit **[Welcome to EchoFlow](README.md)**.

## Before we begin

EchoFlow is still pre-production. There is no polished desktop installer yet, so the
current path uses Python 3.12, `uv`, and the command line.

The workflow itself is local-first:

```mermaid
flowchart LR
    A[Your recording] --> B[Inspect source + computer]
    B --> C[Choose a safe local plan]
    C --> D[Transcribe]
    D --> E[Canonical transcript]
    E --> F[Exports]
    E --> G[Private local search]
    G --> H[Verified evidence navigation]

    classDef evidence fill:#F9D5E5,stroke:#7B2E52,stroke-width:2px,color:#22151B
    classDef compute fill:#D8EEFF,stroke:#2E617B,stroke-width:2px,color:#12222A
    classDef process fill:#E8D9FF,stroke:#68469B,stroke-width:2px,color:#1F1630
    classDef publish fill:#FFF0B8,stroke:#8A6B18,stroke-width:2px,color:#2C260F
    classDef result fill:#DDF5E3,stroke:#347A46,stroke-width:2px,color:#142719

    class A evidence
    class B,C compute
    class D process
    class E,F publish
    class G,H result
```

The original recording is treated as read-only input. EchoFlow writes working files,
checkpoints, transcripts, exports, user-authored state, and search state separately.

## 1. Install the source build

```bash
git clone https://github.com/SSD1805/EchoFlow.git
cd EchoFlow
uv sync --locked --extra transcription
```

Initialize EchoFlow's private application directories:

```bash
uv run echoflow init
```

Then ask EchoFlow to inspect the machine:

```bash
uv run echoflow doctor
uv run echoflow runner
```

`doctor` checks important local dependencies and configuration. `runner` shows the
compute and memory EchoFlow can actually use.

You do **not** need to manually translate that into “therefore I should use four threads,
CUDA device zero, and model X.” That is application work.

## 2. Install a transcription model

Ask EchoFlow which managed model fits the machine and processing policy:

```bash
uv run echoflow models recommend
```

Then install the model you intend to use. For example:

```bash
uv run echoflow models install small
```

Downloading model weights is a network-bearing action, so EchoFlow makes installation
explicit. Once a verified managed model is local, transcription uses that immutable
revision instead of silently reaching out to the network.

🦝 **Raccoon translation:** downloading the toolbox and using the toolbox are different
things.

## 3. Inspect a recording before doing the work

A dry run tells EchoFlow to inspect the media and machine and build a plan without
starting recognition:

```bash
uv run echoflow transcribe interview.m4a --dry-run
```

For machine-readable output:

```bash
uv run echoflow transcribe interview.m4a --dry-run --json
```

## 4. Transcribe locally

```bash
uv run echoflow transcribe interview.m4a
```

EchoFlow may need to decode or normalize the selected audio stream into a deterministic
working format. That working audio is private derived state. Your original recording is
not overwritten.

The current faster-whisper path also asks for native word timing. Those word intervals
are validated and rebased onto one source-relative timeline so internal work chunks do
not reset the published clock.

The durable transcript is canonical JSON. If you also want ordinary reading/subtitle
formats:

```bash
uv run echoflow transcribe interview.m4a --export txt --export srt --export vtt
```

TXT, SRT, and WebVTT are publication views. They can be regenerated from canonical JSON
without running speech recognition again.

## 5. If something interrupts the job

Long recordings and laptops occasionally have opinions.

When a job has durable checkpoints, resume it with the original input and job ID:

```bash
uv run echoflow transcribe interview.m4a --resume JOB_ID
```

Resume is deliberately conservative. EchoFlow rechecks source identity and current
resources and restores the original execution contract rather than silently switching
models, streams, preprocessing, or alignment halfway through the evidence trail.

## 6. Optional: clean up a noisy recording

```bash
uv run echoflow transcribe noisy-interview.wav --enhance
```

Enhancement is off by default. The processed audio remains private working material and
does not replace the source recording. EchoFlow verifies that preprocessing did not
shift the timeline used for transcript evidence.

For the engineering contract, see
**[Local speech enhancement](architecture/speech-enhancement.md)**.

## 7. Optional: anonymous speakers

The intended CLI surface is:

```bash
uv run echoflow transcribe focus-group.wav --diarize
```

Diarization uses anonymous recording-scoped labels such as `speaker-01` and
`speaker-02`. EchoFlow does not treat them as biometric identities or link them across
recordings.

**Current limitation:** the integrated pyannote path is held behind a dependency security
gate while the locked Lightning version is affected by a compensated advisory. While
that gate is active, EchoFlow refuses diarization before model execution/acquisition.

Once speaker evidence exists in a canonical transcript and the library has been rebuilt,
you can give one anonymous ref a durable human-facing name:

```bash
uv run echoflow library speakers list JOB_ID
uv run echoflow library speakers name JOB_ID speaker-02 "Dr. Chen"
```

You name `speaker-02` once for that canonical transcript generation. You do not edit each
occurrence by hand.

For a handoff/overlap-aware transcript view:

```bash
uv run echoflow library speakers transcript JOB_ID
```

See **[Give the anonymous speakers names](speaker-names.md)**,
**[Anonymous speaker diarization](architecture/diarization.md)**, and
**[SECURITY.md](../SECURITY.md)** for the exact boundaries.

## 8. Build and search your local transcript library 🔎

Once you have completed canonical transcripts, build the private lexical library:

```bash
uv run echoflow library rebuild
```

Search it:

```bash
uv run echoflow library search "housing insecurity"
```

Ask for one neighboring canonical segment on each side:

```bash
uv run echoflow library search "housing insecurity" --context-segments 1
```

Filter by anonymous evidence refs or language when useful:

```bash
uv run echoflow library search \
  "rent increase" \
  --speaker speaker-02 \
  --language en
```

If `speaker-02` has a current user label, the human result can show
`Dr. Chen (speaker-02)` while JSON keeps the raw anonymous ref and exposes the friendly
label separately.

Lexical results with aligned word evidence can highlight the exact canonical words that
matched and expose the first match as a source seek coordinate. Semantic-only results
stay passage-level rather than inventing an exact word.

Inspect one transcript's evidence receipt:

```bash
uv run echoflow library show JOB_ID
```

The search databases are rebuildable projections. The navigation layer re-verifies the
canonical transcript before presenting precise evidence coordinates.

Read **[From search result to the exact evidence](evidence-navigation.md)** for the
human explanation.

## 9. Optional: search by meaning, not only matching words ✨

Lexical search is excellent when the transcript contains the words you remember.
Semantic search helps when you remember the idea but not the wording.

A query like:

```text
people struggling to afford housing
```

may help surface:

```text
I was spending almost seventy percent of my pay on the apartment.
```

Those sentences share little vocabulary, but they express a related idea.

EchoFlow's current semantic foundation uses a local sentence-embedding model and private
rebuildable vectors. Search results still point back to original canonical transcript
evidence.

### Is this sent to a hosted AI service?

Not during semantic indexing or search in the current implementation. The embedding
provider loads from a local immutable model snapshot. Acquiring model weights is a
separate network-bearing action.

### Is semantic search part of the normal install yet?

Not quite.

The locked project dependency graph does not yet include Sentence Transformers, so the
semantic path currently expects an environment that already supplies a compatible local
runtime and Multilingual E5 Small snapshot. Lexical search works without any of this.

Read **[Semantic search, without the mystery box](semantic-search.md)** for the full
plain-language explanation.

## What EchoFlow stores 🦝

```mermaid
flowchart LR
    A[Original recording] -->|read only| B[Canonical transcript]
    B --> C[TXT / SRT / VTT]
    B --> D[Lexical search state]
    B --> E[Optional semantic search state]
    B --> N[Verified navigation views]
    A --> F[Private working audio + checkpoints]
    U[User speaker labels] --> N

    classDef evidence fill:#F9D5E5,stroke:#7B2E52,stroke-width:2px,color:#22151B
    classDef derived fill:#D8EEFF,stroke:#2E617B,stroke-width:2px,color:#12222A
    classDef work fill:#E8D9FF,stroke:#68469B,stroke-width:2px,color:#1F1630
    classDef user fill:#FFF0B8,stroke:#8A6B18,stroke-width:2px,color:#2C260F

    class A,B evidence
    class C,D,E,N derived
    class F work
    class U user
```

The useful distinction is not “database versus file.” It is **can this be reconstructed
without losing something the user authored or relied on as evidence?**

- The original recording is source evidence.
- Canonical transcript JSON is the authoritative transcript artifact.
- Speaker display labels are durable user-authored state.
- Future notes/tags/annotations/collections belong to that same durable class.
- TXT/SRT/VTT, search indexes, and navigation views are derived and rebuildable.
- Working audio and most execution material are private processing state.

Delete a search index? Rebuild her.

Delete the only canonical transcript or somebody's annotation? That is data loss.

## Where do I go when I want more detail?

**[docs/README.md](README.md)** is the documentation lobby.

The **[architecture index](architecture/README.md)** is the maintenance hatch for
contributors and technically curious readers. It covers resource admission, media and
timeline semantics, model custody, diarization, enhancement, checkpoints, search, and
canonical evidence navigation in exact terms.

The **[security policy](../SECURITY.md)** defines what “local-first” protects and what it
does not claim.

And if the documentation suddenly starts discussing `FLOAT[]`, cgroup ceilings, or RRF
constants, you have probably wandered into the engine room. 🧜‍♀️
