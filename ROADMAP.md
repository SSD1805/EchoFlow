# EchoFlow roadmap

EchoFlow is being built as a local-first, privacy-conscious, resource-aware audio
processing application. The goal is not to compete with speech-recognition engines
on model quality. EchoFlow should make local processing dependable on the hardware
people already own and keep useful artifacts portable, inspectable, and recoverable.

The project is intended to remain useful without mandatory hosted transcription
fees or a cloud account. Cost awareness means respecting CPU, memory, disk, and
model-storage constraints rather than assuming a high-end GPU. Privacy-first means
local execution by default, explicit network authorization where a capability
requires model retrieval, minimized sensitive metadata, and clearly separated
private recovery state and public user artifacts.

The primary engineering priorities are:

- **Durability and recovery.** Long-running work should survive ordinary process or
  system failure without silently changing the execution contract.
- **Performance and resource awareness.** Plans should fit the CPU, memory, and
  storage actually available to the process, including modest consumer machines.
- **Reproducibility and provenance.** Canonical artifacts should preserve enough
  source and execution identity to explain how they were produced.
- **Privacy boundaries.** Sensitive recordings, transcript fragments, paths, model
  state, and public exports should have explicit and testable handling rules.
- **Small mandatory surface area.** Heavier capabilities should remain optional so a
  user who only needs transcription does not inherit unrelated analysis machinery.

## Near-term direction

The next development sequence is intentionally evidence-driven:

1. Harden private local storage consistently across supported operating systems.
2. Evolve the canonical transcript contract so future speaker, language, confidence,
   and timestamp enrichment has stable optional fields without changing today's
   transcription behavior.
3. Separate ASR execution from optional capabilities such as alignment, diarization,
   and language identification without creating a general plugin platform.
4. Calibrate real execution on representative Windows, macOS, and Linux hardware,
   including peak memory, CPU behavior, decode overhead, checkpoint overhead, and
   interruption/resume.
5. Add TXT, SRT, and WebVTT as deterministic views derived from canonical transcript
   data rather than additional sources of truth.
6. Research optional local speaker diarization and the resource/privacy implications
   of candidate engines.
7. Research a rebuildable local transcript library and search index. DuckDB is a
   candidate for this analytical/search layer; canonical transcript files would
   remain authoritative so the index can be deleted and rebuilt.

## Research candidates

These are directions to investigate, not committed release promises:

- multilingual and code-switching behavior with language attribution below the job
  level;
- multiple local ASR engine adapters when they provide a meaningful hardware,
  accuracy, or deployment advantage;
- anonymous speaker diarization and timestamped speaker turns without silently
  creating a biometric identity database;
- local lexical and metadata search across transcript collections;
- optional semantic embeddings and hybrid lexical/semantic retrieval;
- cross-transcript relationship discovery, clustering, and other research-oriented
  corpus analysis.

The order can change when benchmarks, security review, implementation complexity, or
actual user needs contradict an assumption. The stable direction is narrower:
sensitive local transcription should be dependable, inspectable, portable, and
usable on ordinary hardware.
