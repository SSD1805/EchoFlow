# Security policy

## Current boundary

EchoFlow is a local-first application. It has no cloud transcription integration
or application telemetry. It executes locally resolved FFprobe for inspection,
FFmpeg when audio extraction or normalization is required, and the optional
faster-whisper/CTranslate2 engine for CPU transcription. Local-first describes
where EchoFlow performs its work; it is not a claim that the host operating
system, selected storage, third-party engine, model files, or external executables
are trusted.

The application treats recording names and local paths as potentially
sensitive. Routine logs redact paths by default. Full path logging requires the
explicit `ECHOFLOW_LOG_PATHS=full` setting.

Public failure messages omit input and artifact paths. Human and JSON job-plan
output includes paths because producing that plan is the explicit command
result; callers are responsible for where they store or forward it.

Private state, cache, model, and per-job directories use a platform-specific
private-storage policy. On POSIX, private directories are tightened and verified
as `0700`, and private file writes are tightened and verified as `0600`. On
Windows, EchoFlow uses the operating system's built-in `whoami.exe` and
`icacls.exe` utilities to resolve the current user SID, reset the path DACL,
remove inherited access, grant that SID full control, and verify the resulting
ACL structure. A private operation fails rather than silently continuing when
the current SID or required ACL utility cannot be established.

These controls limit ordinary access through the current operating-system user
boundary; they are not application-level encryption. A local administrator,
process with equivalent privileges, compromised user session, backup product, or
storage snapshot may still access private state. Public transcript artifacts
remain ordinary user files. EchoFlow does not currently encrypt artifacts at
rest; storage encryption is an operating-system or volume responsibility.

## Supported versions

EchoFlow is pre-release software. Security fixes are applied to the current
`main` branch.

## Reporting a vulnerability

Use GitHub's private vulnerability-reporting or security-advisory workflow for
this repository. Do not include sensitive recordings, transcripts, participant
identifiers, access tokens, or private filesystem layouts in a public issue.

Include the affected version or commit, operating system, minimal reproduction,
impact, and whether the issue requires a malicious local file, another local
process, or network access.

## Media inspection boundary

Dry-run inspection resolves a regular local file, restricts FFprobe protocols
to `file`, does not invoke a shell, selects a bounded metadata field
set, enforces a configurable timeout and parser-output limit, and suppresses FFprobe stderr
from public errors. EchoFlow records a full SHA-256 digest and rejects a file
whose size, modification time, device, or inode changes during inspection.

The output limit is checked after the child process exits, so it bounds JSON
parsing but not the memory already consumed by `subprocess.run`. FFprobe remains
native media-parsing code operating on user-selected input.

## Decode and transcription boundary

For media that is not already canonical mono 16 kHz PCM audio, EchoFlow invokes
FFmpeg without a shell or stdin, restricts input protocols to `file`, explicitly
maps the audio stream selected by FFprobe, discards video/subtitle/data streams,
suppresses native diagnostic output from public failures, and enforces a
configurable process timeout. Normalized audio exists only in the private job
workspace and is removed after the attempt. Filesystem deletion is not secure
erasure.

The faster-whisper package and model weights remain optional. The backend uses CPU
int8 execution with the thread count selected by the runner policy and one model
worker to avoid hidden memory multiplication. It uses local model files by default.
`--allow-model-download` explicitly authorizes the engine's Hugging Face retrieval
for that command; it does not authorize recording upload. EchoFlow records the
engine package version, model name, requested revision, compute type, thread count,
beam size, and language setting in canonical output. Unless an immutable model
revision is configured, model provenance identifies the request but does not prove
immutable model content.

Canonical transcript JSON omits the source path, source filename, and model-cache
path. It retains the input SHA-256, size, modification timestamp, container, audio
stream index, and media duration for provenance. Command result envelopes include
job and artifact paths because those paths are an explicit result of the command.

## Checkpoint and resume privacy boundary

Interrupted transcription work is checkpointed only inside EchoFlow's private local
job directory. Durable checkpoints do not use the operating-system temporary
directory because they must survive process restarts and reboots. Disposable audio
segment files remain temporary implementation data and are removed after each
attempt.

Checkpoint manifests omit the input path, source filename, and model-cache path.
They bind the work to the input SHA-256 and media identity, engine/model/revision,
decode configuration, segmentation schema, and exact PCM frame windows. Completed
segment payloads contain the recognized transcript text required to resume exactly;
that text is not masked because masking would change the recovered transcript.
Checkpoint files are atomic private writes. Their private file/directory protection
is enforced through the same POSIX-mode or Windows-DACL policy described above.

Resume accepts only a contiguous prefix of completed segments whose manifest,
window identity, and payload integrity checks match the current transcription
contract. Corrupt, unknown, reordered, mismatched, or oversized checkpoint files
fail closed. A resumed job with completed work will not authorize model retrieval
from the network, and the installed engine package version must match the version
recorded by the completed checkpoints.

Routine checkpoint and resume logs contain only job/segment identifiers, counts,
status fields, and exception types. They do not contain transcript text or source
paths. After the final canonical transcript is published successfully, EchoFlow
removes checkpoint payloads on a best-effort basis. Interrupted jobs retain them so
that recovery remains possible. Deletion is ordinary filesystem deletion, not
secure erasure; backups, snapshots, swap, SSD remapping, privileged local actors,
and same-user processes remain outside this guarantee.

## Processing risks still outside the implemented boundary

FFmpeg and the transcription engine still execute in the EchoFlow process/user
security context rather than an operating-system sandbox. Model signatures,
process-wide network egress enforcement, hard CPU limits, adversarial-media test
corpora, application-level encryption, and secure deletion are not implemented.
Memory admission is a conservative preflight check, not a hard runtime memory cage.
Private-storage ACLs and mode bits do not protect against a compromised user account,
local administrators, or equivalent privileged processes. These properties must not
be inferred from local-first.
