# Give the anonymous speakers names 👥✨

Diarization gives EchoFlow useful but intentionally anonymous evidence:

```text
speaker-01
speaker-02
speaker-03
```

That is good provenance and inconvenient human memory. EchoFlow therefore keeps two different facts:

- `speaker-02` is machine-produced diarization evidence;
- `Dr. Chen` is a name **you** assigned to that anonymous speaker in one exact transcript generation.

The friendly label never rewrites the evidence underneath it.

## Desktop

From a Library transcript result, open **Transcript tools**. The **Name anonymous speakers** section shows the anonymous evidence ref beside an editable display name. Saving `Dr. Chen` produces presentation such as:

```text
Dr. Chen · speaker-02
```

Removing the display name removes only the human-authored label. The anonymous ref remains canonical/diarization identity.

The desktop also exposes **Open speaker transcript**, which presents backend-derived spans as **Speaker**, **Overlap**, **Mixed speakers**, or **Unattributed**. When two speakers are simultaneously active, EchoFlow lists both rather than choosing a winner.

See **[Transcript and speaker tools](transcript-tools.md)** for the desktop authority, publication, security, and testing contract.

## CLI

Inspect anonymous refs:

```bash
echoflow library speakers list TRANSCRIPT_ID
```

Assign a display label:

```bash
echoflow library speakers name TRANSCRIPT_ID speaker-02 "Dr. Chen"
```

Remove it:

```bash
echoflow library speakers forget-name TRANSCRIPT_ID speaker-02
```

Read the derived speaker presentation:

```bash
echoflow library speakers transcript TRANSCRIPT_ID
```

Every command also supports `--json` for machine-readable output.

## Why not replace `speaker-02` with the name?

Those statements come from different authorities.

Diarization says:

> this voice cluster received the recording-scoped anonymous reference `speaker-02`.

You say:

> I know this person is Dr. Chen, so show me that name while I work.

Overwriting one with the other would destroy the distinction between machine-produced evidence and human knowledge. That distinction matters for reproducibility, correction, auditing, search, and durable research.

## Generation binding

Speaker numbering is meaningful only inside the canonical transcript generation that produced it. A re-transcription can change speaker boundaries, and tomorrow's `speaker-02` could represent somebody different from today's `speaker-02`.

A display label is therefore bound to:

```text
transcript ID
+ exact canonical transcript SHA-256
+ anonymous speaker ref
```

If the canonical transcript changes, EchoFlow keeps old user-authored label state but does not silently apply it to the new generation.

This rule is especially important in a long-lived desktop view. Every transcript-tools inspect, speaker transcript, set-label, remove-label, and publication request carries the exact canonical SHA-256 the user opened. Python checks that expected generation at the service/mutation boundary. If the library changed meanwhile, the request fails and the user reopens the current transcript rather than mutating reused speaker numbering.

## Handoffs and overlap

Word-level timing matters. A mixed ASR segment may have no single segment-level `speaker_ref` because the speaker changes halfway through. Individual aligned words can still carry `speaker-01` and `speaker-02` evidence.

The speaker-label service inspects both segment-level and aligned-word speaker evidence, so those speakers remain available to name even when the enclosing sentence cannot honestly be assigned to one person.

The derived speaker transcript combines canonical word timing with the preserved speaker-turn timeline:

```text
00:00:04.100  Interviewer (speaker-01)       single-speaker  What happened next?
00:00:05.900  Dr. Chen (speaker-02)          single-speaker  We moved the samples.
```

If two diarized speakers are simultaneously active over the same aligned word interval, EchoFlow does not choose a winner:

```text
00:00:12.200  Interviewer (speaker-01)
              + Dr. Chen (speaker-02)         overlap         Sorry…
```

If a coarse segment contains more than one speaker but lacks word timing precise enough to assign its text, the view says `mixed-unresolved` rather than pretending the whole sentence belongs to either person.

One conservative rule matters: if a canonical aligned word is unattributed, presentation will not promote it to one named speaker merely because a diarization turn overlaps. Presentation may expose multi-speaker overlap; it does not manufacture a stronger single-speaker claim than canonical evidence supports.

## Search

Ordinary transcript-library search consumes the same current-generation display-label state. Ranking and speaker filters still operate on anonymous evidence refs. Human results may show the friendly label while machine-readable evidence keeps the ref separately.

The navigation layer resolves names only for the exact canonical generation behind the result and batches label lookup per generation.

See **[From search result to the exact evidence](evidence-navigation.md)** for highlighting, context, source seek behavior, and evidence coordinates reused by notes.

## Storage and custody

Speaker names are private user-authored state, not rebuildable search state. They live under EchoFlow's private application state using the atomic private-file boundary, separate from canonical evidence, lexical/semantic indexes, research projection state, and checkpoints.

Rebuilding lexical, semantic, or research projections must not erase names. A later consolidation into the transactional research-state store is possible if it earns its value, but presentation code should continue to depend on the application service rather than a physical adapter.

## Not biometric identification

Speaker display labels are not biometric identification. EchoFlow does not infer that `speaker-01` in two recordings is the same person and does not search for somebody's identity from their voice.

Overlap-aware presentation also does not perform source separation. Separating mixed speech into estimated sources would be a materially heavier later capability with its own compute, model-custody, and provenance requirements.

For the underlying diarization evidence/security gate, see **[Anonymous speaker diarization](architecture/diarization.md)**.
