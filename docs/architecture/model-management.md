# Local model management

## Purpose

EchoFlow treats local inference models as versioned execution dependencies rather than
opaque cache entries. Model management gives the application an explicit inventory,
installation, verification, provenance, recommendation, and removal boundary without
inventing a second model storage format or requiring hosted control-plane state.

The first implementation manages faster-whisper models only. It is intentionally
small enough that later local capabilities, including speech enhancement, can reuse the
same custody contracts without inheriting faster-whisper-specific orchestration.

## Ownership and custody

The Hugging Face cache remains the byte-level storage layout consumed by
faster-whisper. EchoFlow does not copy model weights into a private proprietary format.
Instead, EchoFlow owns a private registry of manifests that describes which cached
snapshots it deliberately installed and verified.

A cached model is therefore not automatically an EchoFlow-managed model. EchoFlow
claims management only after an explicit install succeeds and a private manifest is
committed. Arbitrary pre-existing cache contents remain untracked until a future
explicit adoption workflow exists.

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
For faster-whisper it derives cache-size and quality metadata from the existing
transcription strategy catalog rather than duplicating execution policy.

`ModelManager` owns the application workflow: offline inventory, explicit install,
manifest custody, revalidation, resolved-revision lookup, and removal.

`ModelProvider` owns provider-specific mechanics such as downloading a Hugging Face
snapshot, validating its provider layout, and deleting an exact cached revision.

`ModelStorageAdmitter` is a small application port used before downloads. The current
application container adapts EchoFlow's existing disk-admission policy to that port so
model management does not depend on transcription internals.

## Install transaction

A model install follows this ordering:

1. Resolve the model ID through the catalog.
2. Reject an invalid or blank requested revision.
3. Admit the catalog's estimated cache requirement against current disk capacity.
4. Create the private model/cache/registry directories only after admission succeeds.
5. Ask the provider to acquire the requested repository and revision.
6. Reject any returned snapshot outside EchoFlow's configured model cache before
   inspecting its contents.
7. Bind the snapshot path to the declared provider repository cache directory.
8. Require the snapshot directory name to equal the resolved revision recorded for the
   install.
9. Verify the provider-specific required files exist and are non-empty.
10. Measure the installed snapshot and construct provenance.
11. Commit the private EchoFlow manifest last.

The ordering is intentional. A disk-admission failure cannot start a large download.
A failed or malformed provider result cannot create a managed manifest. A manifest is
therefore evidence of a completed application-level install transaction, not merely an
attempt.

## Inventory and local revalidation

Inventory and resolved-revision lookup are offline and side-effect free. They do not
create directories, download models, or repair cache state.

When a managed manifest exists, EchoFlow validates it before reporting the model as
managed or using its revision in a new plan. Validation checks:

- manifest identity matches the catalog model and repository;
- the snapshot remains inside the configured model cache;
- the snapshot belongs to the declared provider repository cache directory;
- the snapshot path agrees with the recorded resolved revision;
- the recorded verification method is supported; and
- the provider's required files still exist and remain non-empty.

If external deletion or tampering makes a manifest stale, EchoFlow fails closed instead
of treating the old receipt as proof that the model is usable.

This first verification method establishes structural/provider provenance. It does not
claim an independently maintained cryptographic allowlist for upstream model weights.
A future provider may add stronger digest or signature evidence without changing the
application-level custody contract.

## Transcription plan pinning

New transcription plans resolve the model revision with this precedence:

1. an explicit operator-configured revision;
2. the verified resolved revision from EchoFlow's managed registry; or
3. no explicit revision when neither exists.

An explicit operator revision is never silently replaced by registry state. A managed
revision improves reproducibility because a plan records the immutable snapshot that
was locally verified instead of depending on a moving provider default.

Resume does not re-plan model identity. Existing checkpoint semantics remain
authoritative so an interrupted job restores the revision already recorded in its
execution contract.

## Removal transaction

Removal is deliberately asymmetric with installation:

1. Resolve and validate the managed manifest.
2. Reconstruct the exact installed snapshot identity.
3. Ask the provider to remove that resolved revision from the local cache.
4. Delete the EchoFlow manifest only after provider removal succeeds.

If provider removal fails, the manifest is retained. EchoFlow must not claim that it
forgot ownership while the managed bytes may still remain on disk.

The current CLI requires confirmation unless `--yes` is supplied.

## User surface

The first CLI surface is intentionally explicit:

- `echoflow models` lists the offline managed inventory;
- `echoflow models recommend` reuses the current resource-aware transcription strategy
  planner and reports whether the recommended model is managed;
- `echoflow models install MODEL` explicitly authorizes provider network acquisition,
  verifies the resulting snapshot, and records provenance; and
- `echoflow models remove MODEL` removes an exact managed revision after confirmation.

The existing transcription `--allow-model-download` path remains a compatibility seam
in this tranche. It can be reconsidered after managed installation has survived normal
use and resume scenarios; model management does not silently remove an established
execution path underneath durable jobs.

## Failure and privacy semantics

Registry manifests and model storage live under EchoFlow's private application model
root. Inventory and recommendation do not contact the network. Installation is the
explicit network-bearing operation.

Public errors intentionally describe the application failure without leaking internal
paths. Corrupt registry data, path escape, repository mismatch, stale snapshots,
verification failure, storage refusal, and provider removal failure all fail closed.

No transcript, source media, job metadata, or telemetry is sent to the model provider
as part of model management.

## Extension contract for future local models

Speech enhancement should reuse these application concepts rather than creating an
independent downloader and cache registry:

- a capability-specific catalog can describe provider/model choices;
- provider adapters can implement their own structural or cryptographic verification;
- the same private manifest/provenance boundary can record resolved revisions;
- disk admission must happen before acquisition;
- inventory remains offline; and
- execution planners consume verified model identity through a narrow application
  port.

The shared abstraction should be generalized only when a second real provider exposes
the necessary variation. The current implementation deliberately avoids a speculative
universal model marketplace.

## Out of scope for the first tranche

The first tranche does not provide:

- automatic model updates or background downloads;
- adoption of arbitrary pre-existing cache entries as managed state;
- generic support for arbitrary model hubs;
- model garbage collection or quota management;
- hosted telemetry or a remote inventory service;
- simultaneous management of speech-enhancement models before an enhancement provider
  is selected; or
- a promise that structural required-file verification is equivalent to independent
  cryptographic attestation of upstream weights.

The stable rule is narrower: EchoFlow should know which local model dependency it chose,
where it came from, which immutable revision it verified, whether it is still present,
and when it is safe to remove it.
