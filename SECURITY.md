# Security policy

## Current boundary

EchoFlow is a local-first application. It has no cloud transcription integration or
application telemetry. It executes locally resolved FFprobe for inspection, FFmpeg for
canonicalization and optional noise suppression, faster-whisper/CTranslate2 for ASR,
and optional local enrichment dependencies such as pyannote when their security gate
permits execution.

Local-first describes where EchoFlow performs work. It is not a claim that the host
operating system, selected storage, third-party libraries, model files, native media
parsers, or external executables are trusted.

Recording names, transcript content, research notes, tags/collections, and local paths
may all be sensitive. Routine logs redact paths by default. Full path logging requires
explicit `ECHOFLOW_LOG_PATHS=full`.

Public failure messages omit input/artifact paths and should not expose note bodies or
other unexpected internal research content. Human and JSON command results may include
paths, transcript evidence, or note content when those values are an intentional command
result; callers control where those results are stored or forwarded.

## Private local storage

Private state, cache, model, per-job, and research-state directories use platform-specific
access controls. POSIX private directories/files are tightened and verified as
`0700`/`0600`. On Windows, EchoFlow uses built-in identity/ACL utilities to resolve the
current user, remove inherited access, grant the current SID access, and verify the
resulting DACL. A private operation fails rather than silently continuing when the
required identity or ACL enforcement cannot be established.

These controls protect the normal current-user filesystem boundary. They are not
application-level encryption. Local administrators, equivalent privileged processes,
a compromised user session, backups, snapshots, swap, or storage remapping may expose
private state. EchoFlow does not claim secure erasure.

Public transcript artifacts remain ordinary user files. At-rest encryption is an OS,
volume, or storage responsibility today.

## Custody deletion and retention boundary

Normal transcription, indexing, research, navigation, and playback preparation continue
to treat the original recording as read-only source evidence. Deletion is a separate
explicit custody operation, not a side effect of processing, playback, or library rebuild.

`echoflow library delete` is plan-first. Without `--confirm`, it reports the exact current
canonical generation, effective deletion scopes, concrete mutations, preserved attached
notes, affected document-scoped saved searches, and a confirmation value. Execution
recomputes the plan and refuses a stale confirmation.

The `canonical-transcript` scope may remove canonical JSON plus its disposable descendants:
active lexical/semantic retrieval state, regenerable TXT/SRT/VTT publications, and the
private execution workspace. It does not imply deletion of attached research notes,
saved searches, or source media.

Deleting the original recording requires all of the following:

- explicit `source-recording` scope;
- the separate `--allow-source` safety switch;
- an available source path; and
- current source integrity equal to the source SHA-256 recorded for transcription.

If bytes at the source path changed, EchoFlow refuses to delete them. A historical
transcription provenance record is therefore not treated as authorization to delete new
bytes that later occupied the same path.

Immediately before canonical deletion, EchoFlow re-reads the canonical JSON and verifies
its SHA-256 against the indexed generation. A changed or missing canonical artifact fails
closed before any mutation.

Age-based retention is narrower than explicit deletion. It can delete only private
per-job execution workspaces. Completed jobs are eligible by default; failed/interrupted
jobs require explicit inclusion because cleanup removes resume capability; running jobs
are never eligible. Retention preserves canonical/public evidence, user-authored research
state, source media, and lightweight lifecycle manifests.

SQLite, DuckDB, public files, private workspaces, and arbitrary source paths cannot share
one cross-filesystem ACID transaction. The custody executor therefore validates destructive
inputs first and orders rebuildable/regenerable state before unique human-authored state.
A later failure may leave earlier disposable cleanup already applied, but should not erase
unique research first and hope filesystem cleanup succeeds afterward.

The confirmation value is a plan-change detection primitive, not an authentication secret.
It does not authorize a caller who lacks normal filesystem/application access.

EchoFlow's deletion APIs remove paths/state through normal operating-system and database
mechanisms. They do **not** claim cryptographically or physically verifiable secure erasure
from SSD wear-levelled blocks, copy-on-write history, snapshots, backups, sync/version
history, controller caches, or forensic recovery outside the active namespace.

## Research-state privacy boundary

Research notes, tags, collections, evidence anchors, and saved searches are durable private
user-authored state. They may reveal participant identities, research hypotheses,
interpretations, case themes, or other information that is at least as sensitive as
transcript text.

EchoFlow stores research state in an authoritative private SQLite database. The database
may contain:

- note prose;
- tag and collection names;
- note-to-tag and note-to-collection relationships;
- exact source/canonical evidence anchors;
- saved typed query intent; and
- the monotonic change journal used to drive projection convergence.

The separate DuckDB research database is a **rebuildable private projection**, not public
or disposable in the privacy sense. It may contain note IDs, canonical evidence keys,
tag/collection IDs, projected relationships, and deterministic lexical terms derived from
note text. Those values can still disclose research semantics even though authoritative
note prose remains in SQLite.

SQLite and DuckDB are not attached and do not share a cross-database transaction. User
mutations commit only to authoritative SQLite with their journal event; a deterministic
projector later updates DuckDB. Deleting or rebuilding the DuckDB research projection must
never delete SQLite user state.

Neither database is encrypted by EchoFlow today. They rely on the private filesystem
boundary described above and any OS/volume encryption the user configures.

Research indexing/search does not upload notes, tags, collections, evidence anchors,
saved searches, or projection contents. EchoFlow has no hosted note synchronization or
research telemetry.

If a canonical transcript generation changes or is explicitly deleted, existing notes
remain durable historical state unless the user separately selects the `research-notes`
deletion scope. They are not silently re-anchored or cascade-deleted. Saved searches are
also preserved unless their own explicit deletion scope is selected.

## Supported versions

EchoFlow is pre-release software. Security fixes apply to current `main`.

Because the project has not been released or meaningfully dogfooded, internal durable
contracts currently use one canonical schema rather than migration branches for
unreleased development states. This does not weaken validation: unsupported schema
versions fail closed. A real migration policy should begin when an actual released or
dogfooded compatibility boundary exists.

## Reporting a vulnerability

Use GitHub private vulnerability reporting/security advisories. Do not include sensitive
recordings, transcripts, participant identifiers, research notes, tags, collection names,
tokens, or private filesystem layouts in a public issue.

Include the affected commit/version, operating system, minimal reproduction, impact,
and whether exploitation requires a malicious local file, another local process, or
network access.

## Media inspection boundary

Dry-run and Processing Center inspection resolve a regular local file, restrict FFprobe
protocols to `file`, do not invoke a shell, select bounded metadata fields, enforce timeout
and parser-output limits, and suppress native stderr from public errors.

The primary FFprobe query remains the normal inspection contract. If that bounded query
discovers more than one audio stream, EchoFlow performs one additional bounded,
file-protocol-only metadata query for stream index, title, language, and default disposition.
Title and language are length-bounded before they can enter the media model or desktop DTO.
They remain untrusted source-declared display metadata, not a recommendation or source
identity claim.

EchoFlow fingerprints the complete input with SHA-256 and rejects a file whose observed
filesystem identity changes during inspection. `AudioStreamSelector` then selects the
first audio stream by low-level deterministic default or a validated explicit
`--audio-stream INDEX`/desktop stream index. The selected stream becomes part of
source/checkpoint provenance rather than an incidental FFmpeg argument.

Processing Center does not treat the deterministic probe default as user intent when
several embedded audio streams exist. Python marks the first preflight as requiring
explicit stream confirmation. React can present the bounded stream metadata and return an
integer choice, but Python validates/replans the exact stream before execution.

The output limit bounds parsed FFprobe JSON after each process returns; it is not a hard
memory cage for the native child process. FFprobe remains native media-parsing code
operating on user-selected input.

## Decode and preprocessing boundary

For media not already canonical mono 16 kHz PCM16 WAV, EchoFlow invokes FFmpeg without
a shell/stdin, restricts input protocols to `file`, maps exactly the selected audio
stream, discards video/subtitle/data and unrelated audio streams from the working path,
suppresses native diagnostics from public failures, and enforces a configurable process
timeout.

Normalized audio is private derived state in the job workspace and is removed after the
attempt where possible.

With explicit `--enhance`, EchoFlow runs a second local FFmpeg transform using the
application-owned `afftdn=nf=-50:nr=12` contract. Enhanced audio is also private derived
state and is never published automatically or treated as source truth.

Enhancement fails closed if FFmpeg is unavailable, its runtime version cannot be
recorded, the requested provider/parameters differ from the planned contract, filtering
fails, or the result changes channel count, sample width, sample rate, or frame count.
These checks protect the source-relative timeline contract from hidden trimming,
padding, resampling, or channel changes.

ASR consumes enhanced audio only when enhancement succeeded. EchoFlow does not silently
fall back to raw ASR after a requested enhancement failure. Anonymous diarization still
consumes the unmodified canonical decode in enhancement v1.

## Verified playback boundary

Playback is not path-driven from React. A webview request contains only a document ID, the
exact canonical SHA-256 already opened in the evidence view, and a finite non-negative
source-relative seek coordinate.

Python playback authorization re-reads and hashes canonical JSON, verifies source/job
identity, probes the remembered original recording, verifies current source SHA-256 and
size, checks duration bounds, and verifies audio-stream identity. Changed/missing source
bytes, stale generations, invalid coordinates, and ambiguous multi-audio sources fail
closed.

The path-bearing playback grant is private to the fixed Rust host; it is not exposed as a
general Tauri command. Rust opens the approved source, narrows the verify/open race with
metadata checks, and stores the opened file behind an opaque active session ID. React
receives only opaque session/media state and safe coordinates.

The dedicated `echoflow-media` protocol accepts active closed-shape session IDs rather than
paths, permits only `GET`/`HEAD`, rejects multipart/invalid ranges, caps each response body
at 1 MiB, limits active sessions, and uses `Cache-Control: no-store`. The CSP allows this
dedicated media protocol rather than general `file:`, `blob:`, or arbitrary localhost media.

Multi-track transcription and playback intentionally have different support levels.
Transcription owns exact FFmpeg stream extraction and can prove which stream entered ASR.
Current system-WebView playback of the original container cannot portably prove which
embedded audio stream was rendered, so multi-track playback remains refused instead of
guessing.

## Resource and storage admission

Before claiming the job workspace or decoding media, execution rechecks CPU/memory
admission and source identity. Storage admission compares planned private workspace and
public output allocations with free space, summing allocations that share a filesystem
before applying the configured minimum-free-space floor.

The private workspace estimate includes normalization when needed, optional full-
recording enhanced audio, bounded segment materialization, and fixed workspace headroom.
This is preflight admission, not a quota or reservation. Free space may change after
admission.

Model acquisition uses a separate model-storage admission boundary before network
transfer begins.

## Managed ASR model boundary

Faster-whisper model acquisition is explicit model-management work, not a transcription
side effect.

A model becomes managed only after:

- catalog identity is resolved;
- disk admission succeeds;
- provider acquisition completes;
- returned snapshot path is proven inside EchoFlow's private model cache and bound to
  the expected provider repository;
- resolved revision agrees with snapshot identity;
- required provider files exist and are non-empty; and
- the private manifest is committed last.

Inventory and revision lookup are offline and side-effect free. Existing manifests are
revalidated against local snapshot reality before being trusted.

New ASR plans require a verified managed immutable revision. There is no arbitrary
configuration revision override and no ambient-cache fallback. faster-whisper executes
with `local_files_only=True` and the exact revision in the plan. There is no
`--allow-model-download` transcription flag.

The current verification method proves expected provider layout,
repository/revision identity, and required non-empty files. It does **not** claim an
independent cryptographic allowlist/signature for upstream model weights.

`echoflow models install MODEL` is the explicit network-bearing ASR model action. Model
management never uploads recordings, transcripts, job metadata, or telemetry.

## Checkpoint and resume privacy boundary

Interrupted work is checkpointed inside the private local job directory. Durable
checkpoints do not use OS temporary directories because they must survive process
restarts/reboots. Disposable segment and derived audio files remain transient
implementation state.

The current checkpoint manifest omits source path, source filename, and model-cache path
while binding:

- source fingerprint/media identity and selected audio stream;
- profile/provisional state;
- engine/model/immutable managed revision and execution target;
- decode configuration;
- enhancement off/on/provider/parameters/model identity if applicable;
- segmentation settings and exact PCM frame windows; and
- resource requirements.

Completed checkpoint payloads contain exact recognized text required for recovery. That
text is not masked because masking would change the recovered transcript.

Resume accepts only a contiguous prefix whose manifest, windows, payload integrity,
source identity, engine version, and current resource admission all agree. It never
downloads replacement ASR weights or substitutes a new model revision. Enhancement
cannot be switched on/off or changed during resume because preprocessing identity is
part of the contract digest. The selected embedded audio stream is also restored from the
checkpointed contract rather than reselected from current container defaults.

After canonical publication, checkpoint payloads are removed on a best-effort basis.
Interrupted jobs retain them. Ordinary filesystem deletion is not secure erasure.

## Canonical transcript provenance

Canonical JSON omits source path, source filename, and model-cache path. It retains
source SHA-256, size, modification timestamp, container, exact audio stream, and duration.

The current transcript contract also records managed engine/model/revision and execution
parameters, language evidence, optional anonymous speaker evidence, and optional
enhancement provider/version/operation/parameters. Enhancement provenance explains how
ASR input was transformed; it does not make the derived WAV authoritative or public.

Source-declared track title/language/default metadata shown during multi-track preflight is
not promoted into cryptographic identity. The exact stream index is the durable provenance
coordinate that answers which embedded track was transcribed.

Command result envelopes may include job/artifact paths because those are explicit
command results.

## Diarization security hold

Anonymous speaker diarization is optional. EchoFlow does not perform biometric identity
or cross-recording speaker linking.

The locked pyannote dependency graph currently includes Lightning 2.6.5, affected by
CVE-2026-58659. EchoFlow blocks diarization before pyannote import or model acquisition
until a compatible patched Lightning release is available. The dependency-audit
exception is restricted to the exact advisory/version so dependency drift forces
re-evaluation.

Any current diarization model-download authorization is narrowly scoped to the optional
diarization capability. It is not a general ASR network permission.

## Local file and workspace boundary

Application writes use a temporary file in the destination directory, flush/fsync file
contents, and atomically replace the destination. Private writes apply private-storage
policy before sensitive bytes are written and again to the final destination. Public
artifact names are exclusively reserved so concurrent processes do not silently
overwrite each other.

Job workspace paths derive only from EchoFlow's private jobs directory and validated job
IDs. Planning validates normalized paths before creation/resume mutates the filesystem,
so a pre-existing symlink resolving a planned job path outside the configured jobs root
is rejected.

EchoFlow does not currently perform a cross-platform directory `fsync` after every
atomic replace, so it does not claim that a just-renamed file survives sudden power or
filesystem metadata loss. Process-crash recovery and power-loss durability are separate
guarantees.

## Risks outside the implemented boundary

FFmpeg, FFprobe, ASR, optional model/native dependencies, SQLite, DuckDB, Tauri, and the
system WebView execute in the current process/user security context rather than an OS
sandbox. EchoFlow does not currently provide:

- independent upstream model signatures/allowlists;
- process-wide network egress enforcement;
- hard CPU/RAM/disk runtime cages;
- adversarial-media sandboxing;
- application-level encryption;
- cryptographically or physically verifiable secure erasure;
- malicious same-user TOCTOU protection; or
- protection from a compromised account or local administrator.

Resource admission, private-storage controls, custody-aware deletion/retention, playback
capability narrowing, and the authority/projection split are meaningful safety boundaries,
but none of the stronger properties above should be inferred from “local-first.”
