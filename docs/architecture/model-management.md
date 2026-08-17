# Local model management

## Purpose

EchoFlow treats local inference models as versioned execution dependencies rather than
opaque cache entries. Model management gives the application an explicit inventory,
installation, verification, provenance, recommendation, and removal boundary without
inventing a second model storage format or requiring hosted control-plane state.

The first implementation manages faster-whisper models. Later model-backed local
capabilities should reuse the same custody contracts rather than create parallel
network, cache, and provenance paths.

## Ownership and custody

The Hugging Face cache remains the byte-level storage layout consumed by
faster-whisper. EchoFlow does not copy model weights into a proprietary format.
Instead, EchoFlow owns private manifests describing the exact cached snapshots it
deliberately installed and verified.

A cached model is not automatically an EchoFlow-managed model. Management begins only
after an explicit install succeeds and a private manifest is committed. Arbitrary
pre-existing cache contents are not adopted implicitly.

A managed manifest records at least:

- logical model ID and engine;
- provider repository ID;
- requested provider revision, when supplied;
- resolved immutable revision;
- absolute snapshot path;
- measured snapshot size; and
- verification method.

The manifest is application state, not a copy of the model. The provider cache remains
the physical source of model bytes.

## Components

`ModelCatalog` describes the finite set of models EchoFlow knows how to reason about.
For faster-whisper it derives cache-size and quality metadata from the transcription
strategy catalog instead of duplicating execution policy.

`ModelManager` owns offline inventory, explicit install, manifest custody, local
revalidation, resolved-revision lookup, and removal.

`ModelProvider` owns provider-specific mechanics such as downloading a Hugging Face
snapshot, validating provider layout, and deleting an exact cached revision.

`ModelStorageAdmitter` runs before downloads. The application container adapts the
shared disk-admission policy to this port so model management does not depend on
transcription internals.

## Install transaction

A model install follows this ordering:

1. Resolve the model ID through the catalog.
2. Reject an invalid or blank requested revision.
3. Admit the catalog's estimated cache requirement against current disk capacity.
4. Create private model/cache/registry directories only after admission succeeds.
5. Ask the provider to acquire the requested repository and revision.
6. Reject any returned snapshot outside EchoFlow's configured model cache.
7. Bind the snapshot path to the declared provider repository cache directory.
8. Require the snapshot directory name to equal the resolved revision.
9. Verify provider-specific required files exist and are non-empty.
10. Measure the installed snapshot and construct provenance.
11. Commit the private EchoFlow manifest last.

The ordering is intentional. Disk refusal cannot begin a large download, and a failed
or malformed provider result cannot become managed state.

## Inventory and local revalidation

Inventory and resolved-revision lookup are offline and side-effect free. They do not
create directories, download models, or repair cache state.

When a managed manifest exists, EchoFlow revalidates it before reporting the model as
managed or returning its revision to a planner. Validation checks:

- manifest identity matches the catalog model and repository;
- the snapshot remains inside the configured model cache;
- the snapshot belongs to the declared provider repository cache directory;
- the snapshot path agrees with the recorded resolved revision;
- the recorded verification method is supported; and
- required provider files still exist and remain non-empty.

If external deletion or tampering makes a manifest stale, EchoFlow fails closed instead
of treating an old receipt as proof that the model remains usable.

This verification establishes structural/provider provenance. It does not claim an
independently maintained cryptographic allowlist for upstream model weights. A future
provider may add digest or signature evidence without changing the application custody
boundary.

## Transcription custody boundary

There is one ASR model path.

A new transcription plan must resolve the selected faster-whisper model through the
verified managed registry. If the selected model is not installed and locally
revalidated, planning fails with an install-first error. A successful plan therefore
always records a non-empty immutable resolved revision.

Transcription execution is local-only with respect to ASR model acquisition. The
faster-whisper adapter uses `local_files_only=True` and the exact revision already
recorded in the plan. There is no transcription-time ASR download flag, ambient
Hugging Face cache fallback, or configuration override that can substitute an
unmanaged revision.

Model acquisition happens through the explicit user action:

```text
echoflow models install MODEL
```

Resume restores the exact managed model revision already recorded in the checkpoint
contract. It never replans to a newer revision and never downloads a replacement as a
side effect of resume.

EchoFlow is pre-production, so this contract intentionally replaces earlier
compatibility scaffolding rather than carrying migration branches for behavior that has
not been dogfooded or released.

## Removal transaction

Removal is deliberately asymmetric with installation:

1. Resolve and validate the managed manifest.
2. Reconstruct the exact installed snapshot identity.
3. Ask the provider to remove that resolved revision from the local cache.
4. Delete the EchoFlow manifest only after provider removal succeeds.

If provider removal fails, the manifest is retained. EchoFlow must not claim that it
forgot ownership while managed bytes may still remain on disk.

The CLI requires confirmation unless `--yes` is supplied.

## User surface

The model-management CLI is explicit:

- `echoflow models` lists offline managed inventory;
- `echoflow models recommend` reuses current resource-aware strategy assessment and
  reports whether the recommended model is managed;
- `echoflow models install MODEL` authorizes provider network acquisition, verifies the
  resulting snapshot, and records provenance; and
- `echoflow models remove MODEL` removes an exact managed revision after confirmation.

A normal first transcription flow is therefore:

```text
echoflow models recommend
echoflow models install small
echoflow transcribe recording.m4a
```

The selected model may differ by profile or explicit strategy, so the model required by
a plan must be managed before that plan can execute.

## Failure and privacy semantics

Registry manifests and model storage live under EchoFlow's private application model
root. Inventory and recommendation do not contact the network. Installation is the
explicit network-bearing ASR model operation.

Public errors describe the application failure without leaking internal paths. Corrupt
registry data, path escape, repository mismatch, stale snapshots, verification
failure, storage refusal, and provider removal failure all fail closed.

No transcript, source media, job metadata, or telemetry is sent to the model provider
as part of model management.

## Extension contract for future local models

A future model-backed capability should reuse these concepts:

- a capability-specific catalog may describe provider/model choices;
- provider adapters may implement structural or cryptographic verification;
- private manifests record immutable resolved revisions;
- disk admission happens before acquisition;
- inventory remains offline; and
- execution planners consume verified model identity through narrow application ports.

The first speech noise-suppression provider is intentionally model-free and therefore
does not fabricate a model manifest. If EchoFlow later adopts a neural enhancement
provider with weights, those weights must enter through this custody boundary.

The shared abstraction should be generalized only when a second real model-backed
provider exposes necessary variation. EchoFlow does not need a speculative universal
model marketplace.

## Out of scope

The current tranche does not provide:

- automatic model updates or background downloads;
- adoption of arbitrary pre-existing cache entries as managed state;
- generic support for arbitrary model hubs;
- model garbage collection or quota management;
- hosted telemetry or a remote inventory service; or
- a claim that structural required-file verification equals independent cryptographic
  attestation of upstream weights.

The stable rule is simple: EchoFlow knows which local model dependency it chose, where
it came from, which immutable revision it verified, whether it is still present, and
when it is safe to remove it.
