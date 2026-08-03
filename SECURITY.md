# Security policy

## Current boundary

EchoFlow is a local-first application. The current release foundation has no
network client, cloud integration, telemetry, transcription engine, or model
downloader. It does execute a locally resolved `ffprobe` process for explicit
dry-run media inspection. Local-first describes where EchoFlow performs its
work; it is not a claim that the host operating system, selected storage,
future third-party engines, or external executables are trusted.

The application treats recording names and local paths as potentially
sensitive. Routine logs redact paths by default. Full path logging requires the
explicit `ECHOFLOW_LOG_PATHS=full` setting.

Public failure messages omit input and artifact paths. Human and JSON job-plan
output includes paths because producing that plan is the explicit command
result; callers are responsible for where they store or forward it.

Private state, cache, model, and per-job directories are owner-only on POSIX.
Public transcript artifacts remain ordinary user files. EchoFlow does not
currently encrypt artifacts at rest; storage encryption is an operating-system
or volume responsibility.

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

## Processing risks still outside the implemented boundary

Before EchoFlow decodes or transcribes untrusted media, its FFmpeg and
transcription-engine boundary still needs explicit version policy, time and
resource limits, model provenance, failure isolation, and adversarial-media
testing. Encryption, secure deletion, and process-wide network egress
enforcement are not implemented and must not be inferred from local-first.
