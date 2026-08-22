# Getting started with EchoFlow 💃

This is the **use-the-thing** guide.

EchoFlow is a private, local-first workspace for recorded evidence. You do not need to understand CUDA, DuckDB, SQLite, model revisions, or desktop IPC to use it. Python owns those application/evidence decisions so the desktop can speak in recordings, transcripts, speakers, searches, notes, playback, and evidence.

EchoFlow is still pre-production. There is no polished signed installer yet, so the supported path is a source/developer checkout.

## Pick the smallest setup

| Goal | First command after cloning | You do not need yet |
|---|---|---|
| inspect/click the frontend with fake local data | `cd frontend && npm ci && npm run dev:mock` | Python, uv, Rust, FFmpeg, model |
| run the native desktop window | follow desktop prerequisites, then `npm run tauri dev` | transcription model until processing media |
| use the Python CLI / process recordings | `uv sync --locked --extra transcription` | frontend tooling unless you want the GUI |

If a source build behaves strangely, use **[Desktop source-build troubleshooting](development/troubleshooting.md)**.

## Frontend-only mock path

```bash
git clone https://github.com/SSD1805/EchoFlow.git
cd EchoFlow/frontend
npm ci
npm run doctor:desktop -- --mode=mock
npm run dev:mock
```

`dev:mock` intentionally uses fake local data. Plain `npm run dev` in a browser shows a development-mode explanation rather than pretending the browser has Tauri/Python filesystem authority.

## Native desktop path

Read **[Desktop development prerequisites](development/desktop-development.md)** before the first native build. On a prepared machine:

```bash
cd EchoFlow
uv sync --locked --extra transcription
cd frontend
npm ci
npm run doctor:desktop
npm run tauri dev
```

The debug Tauri host prefers the repository `.venv` for local backend calls.

## Help is built into the desktop

You do not need to keep this guide open beside EchoFlow. The sidebar always offers **How this screen works** for the active workspace and **How EchoFlow works** for the overall evidence model.

Evidence reader, Playback, Transcript tools, and multi-track preflight also expose local explanation beside unfamiliar controls. These explanations are re-openable where appropriate, work with keyboard/touch, and do not rely on hover. They describe existing backend rules without recreating those rules in React.

See **[In-app guidance](in-app-guidance.md)** for the interaction and architecture contract.

## 1. Add or remember recordings

Use **Add evidence** to select recordings, existing transcript JSON, or folders you want EchoFlow to remember. Remembered locations are explicit permissions, not media custody.

Recording discovery does not itself hash, probe, copy, or transcribe candidates. Manual processing remains the default unless you explicitly choose a different processing policy.

## 2. Process a recording

Choose **Processing**. The current control loop includes:

- machine/resource readiness;
- managed model state;
- outcome-oriented processing profile;
- backend preflight before execution;
- explicit embedded-audio-track confirmation when a source contains more than one audio stream;
- optional deterministic enhancement;
- optional anonymous diarization;
- derived publication intent;
- supervised local start/cancel;
- durable job progress/state;
- checkpoint resume versus fresh retry; and
- private execution-state discard that does not delete source media, canonical transcript evidence, or research.

For a normal single-track recording, there is no track choice to make. If preflight finds several embedded audio tracks, Processing Center shows the available tracks and bounded source-declared metadata such as title, language, codec, sample rate, channel count, and container-default status. **Start local transcription** remains disabled until you choose one. EchoFlow then sends that exact index back to Python and re-runs preflight before enabling Start.

Those labels are clues from the source file, not EchoFlow recommendations. A container can call something `Lav microphone` or mark it default without proving that the label is correct.

Long transcription is not an hour-long WebView request. Python plans/admisses/executes; Tauri supervises allowlisted child processes; React presents status and user intent.

See **[Processing Center](architecture/processing-center.md)** and **[Audio tracks](audio-tracks.md)**.

## 3. Process from the CLI when useful

```bash
uv sync --locked --extra transcription
uv run echoflow init
uv run echoflow doctor
uv run echoflow models recommend
uv run echoflow models install small
uv run echoflow transcribe interview.m4a --dry-run
uv run echoflow transcribe interview.m4a
```

For a file with several embedded audio tracks, bind an exact FFmpeg stream index explicitly:

```bash
uv run echoflow transcribe meeting.mkv --audio-stream 3 --dry-run
uv run echoflow transcribe meeting.mkv --audio-stream 3
```

An unavailable or non-audio index fails instead of silently falling back. The selected stream is preserved in canonical source provenance and restored on checkpoint resume.

Publication views can be requested with:

```bash
uv run echoflow transcribe interview.m4a --export txt --export srt --export vtt
```

Resume a validated interrupted job with:

```bash
uv run echoflow transcribe interview.m4a --resume JOB_ID
```

Resume rechecks source identity and current resource admission rather than silently changing the original execution contract.

## 4. Search the Library

```bash
uv run echoflow library rebuild
uv run echoflow library refresh
uv run echoflow library search "housing insecurity"
uv run echoflow library find "housing affordability" --context-segments 1
```

In the desktop **Library**, search transcripts, notes, tags, and collections. A transcript result can open either:

- **Open transcript passage** for exact verified context, the source-relative cursor, and verified playback; or
- **Transcript tools** for transcript/speaker management on that exact canonical generation.

## 5. Play the verified source

Open a transcript passage and choose **Prepare playback**.

EchoFlow does not hand the recording path to React. The request carries only the exact transcript generation and current source-relative cursor. Python re-verifies the canonical bytes, original source fingerprint, duration bounds, and selected audio stream. Rust opens only that approved file and gives the webview an opaque local media session.

After preparation you can use the system audio/video controls or **Play from evidence cursor**. Clicking a timed word moves the same cursor, and preparing/replaying from that cursor uses the verified source-relative coordinate.

Playback is refused when the original recording is missing, its bytes changed, the transcript view is stale, the requested coordinate is invalid, or the source has multiple audio tracks that EchoFlow cannot yet prove the WebView will select correctly. This playback restriction does **not** prevent multi-track transcription: transcription explicitly extracts the user-selected track, while current WebView playback cannot yet prove its rendered embedded track. A verified source can also be unsupported by the local system decoder; that is reported as a codec/container limitation rather than silently transcoding the evidence.

See **[Verified native playback](native-playback.md)** and **[Audio tracks](audio-tracks.md)**.

## 6. Use transcript and speaker tools

From a transcript result, choose **Transcript tools**. EchoFlow verifies `(document_id, canonical_sha256)` before returning details or accepting mutations.

The panel can show:

- verified generation identity;
- duration/language/segment/speaker summary;
- whether the source recording is currently available;
- selected audio-stream and processing provenance under **Technical details**;
- anonymous speaker refs with optional human display names;
- a derived speaker transcript with explicit **Speaker**, **Overlap**, **Mixed speakers**, and **Unattributed** states; and
- post-hoc TXT/SRT/WebVTT publication to a native-selected folder.

Speaker names never replace anonymous evidence refs. If you save `Dr. Chen` for `speaker-02`, the desktop keeps `speaker-02` visible.

If the transcript changed since the view was opened, Python refuses the stale operation rather than applying a name or publication request to a newer generation.

See **[Transcript and speaker tools](transcript-tools.md)** and **[Give the anonymous speakers names](speaker-names.md)**.

CLI speaker tools remain available:

```bash
uv run echoflow library speakers list JOB_ID
uv run echoflow library speakers name JOB_ID speaker-02 "Dr. Chen"
uv run echoflow library speakers transcript JOB_ID
```

## 7. Keep durable research

Notes, tags, collections, anchors, and saved searches are authoritative local user state.

```bash
uv run echoflow library notes add JOB_ID segment-000042 \
  --body "Compare this with the 2024 survey." \
  --tag methodology \
  --collection "Chapter 3"
```

The desktop Research search uses one **Match** choice: Any of these words, All of these words, or Exact phrase. Retrieval, ordering, transcript/speaker/language constraints, research filters, result count, and context live under **Search options**. Technical retrieval provenance stays under **Technical details**.

Research can reopen the exact older canonical generation cited by a durable note. Playback uses that opened generation identity rather than silently substituting the current transcript.

See **[Research search](research-search.md)** and **[Research notes](research-notes.md)**.

## 8. Review storage and retention deliberately

Choose **Storage** to inspect backend-planned custody changes before anything destructive occurs. The desktop can preview exact requested/effective scopes, concrete actions, preserved-note and affected-saved-search counts, and plan-bound confirmation. Source recording deletion requires its own scope and a second acknowledgment before the backend provenance guard can be submitted.

Retention is narrower. It previews old private processing workspaces, excludes running jobs, and visibly marks failed/interrupted candidates whose resume capability would be lost. It does not age-delete canonical transcripts, source recordings, published transcripts, human research, or lightweight lifecycle manifests.

See **[Storage and lifecycle controls](storage-lifecycle.md)**.

## 9. Change the appearance

The header has one **Theme** dropdown with:

- Archive;
- Midnight;
- Paper;
- Moss;
- Plum;
- Ember;
- Pride; and
- Monochrome.

The choice is local presentation preference only. All eight skins use the same semantic tokens for text, surfaces, controls, focus, errors, selection, and accent foreground. Pride's rainbow is decorative; Monochrome is deliberately grayscale. Every registered skin runs through the same contrast/axe qualification.

See **[Desktop themes and accessibility](development/desktop-accessibility.md)**.

## 10. Know the trust boundary

The desktop WebView does not receive arbitrary SQL, shell, subprocess, database, or raw canonical/source filesystem authority.

Ordinary bounded desktop calls share one fixed-command protocol helper and one capability-blind Python host transport. Transcript tools and lifecycle still use separate fixed Tauri commands/Python modules, and playback is narrower still: its path-bearing Python grant is private to Rust, which opens the file and returns only an opaque session to React. Python remains application/evidence authority.

Long-running Processing tasks are intentionally separate from bounded request/response IPC. Tauri owns their supervised child-process lifetime, task identity, status, and cancellation; Python remains job/checkpoint/transcription authority.

Multi-track preflight follows the same rule. Python discovers streams and decides whether explicit confirmation is required. React only presents bounded track metadata and submits the user's chosen index; it does not infer the best track or inspect media itself.

The in-app help layer is static local presentation copy. It has no extra filesystem, process, database, model, media, or network capability.

See **[frontend/SECURITY.md](../frontend/SECURITY.md)** and the completed **[architecture/redundancy audit](architecture/redundancy-audit.md)**.

## 11. Optional semantic/hybrid search

Lexical search is the dependency-light default. Semantic search helps when you remember the idea but not the wording; hybrid retrieval combines lexical/semantic ranking using reciprocal rank fusion.

The semantic foundation remains advanced source-build setup until packaged dependency/model custody is qualified.

See **[Semantic search](semantic-search.md)**.

## What EchoFlow stores

Original media and canonical JSON are evidence. Notes/tags/collections, saved searches, and speaker names are durable human knowledge. Search/research projections and TXT/SRT/WebVTT are derived/rebuildable. Remembered locations and theme selection are machine-local preferences with different custody semantics from evidence. Playback sessions are temporary native capabilities and are not evidence or durable state.

## What comes next?

Research/search, Processing, desktop comprehension/themes, transcript/speaker tools, explicit embedded-track transcription, verified native playback, contextual guidance, lifecycle/retention Storage, and the pre-identity architecture/redundancy audit are foundation. Next:

1. product identity decision and deliberate migration;
2. packaging/first run/update/uninstall;
3. backup/restore and research portability;
4. packaged semantic custody; and
5. representative-device qualification.

For the detailed first-release sequence, see **[ROADMAP.md](../ROADMAP.md)**.
