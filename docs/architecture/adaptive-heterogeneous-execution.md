# Adaptive heterogeneous execution

Status: implemented architecture, representative-device qualification pending  
Last updated: August 17, 2026

## Purpose

EchoFlow should use the machine a recording is actually running on without turning
transcription into a collection of vendor-specific conditionals. A commodity laptop
may have useful CPU capacity, system RAM, and an accelerator that its owner rarely
uses directly. Those resources are not interchangeable, and merely detecting a GPU
does not prove that the installed transcription engine can execute on it.

The adaptive-execution architecture therefore separates four decisions:

1. discover process-visible compute and memory topology;
2. ask each engine adapter which execution targets its installed runtime can really
   use;
3. admit and rank concrete strategies against the current resource budgets; and
4. overlap independent CPU-side preparation with accelerator inference without
   weakening checkpoint ordering or resumability.

This is deliberately not a general tensor-sharding or distributed-compute system.

## Resources are not all compute

CPU cores and accelerators execute work. System RAM and accelerator memory provide
capacity and bandwidth for model weights, buffers, audio, queues, and intermediate
state. EchoFlow models those roles separately.

The existing `RunnerInspector` remains authoritative for process-visible CPU and
system-memory capacity. It already accounts for CPU affinity, Linux cgroup CPU
quotas, Linux cgroup memory ceilings, and current process-visible free memory. The
new `HardwareTopologyInspector` composes that stable inspection with an independent
accelerator probe.

Accelerator memory has an explicit topology:

- **dedicated** memory is a distinct device-memory pool, such as discrete NVIDIA
  VRAM;
- **shared** and **unified** memory consume the same physical capacity available to
  the host and therefore must also count against the system-memory budget;
- **unknown** memory is not guessed. Strategies that require an unknown device-memory
  budget fail closed.

EchoFlow must never add shared or unified accelerator memory to system RAM and call
the result extra capacity. A machine with 16 GiB of unified memory still has 16 GiB
of physical memory, not 16 GiB plus a fictional GPU allocation.

## Physical visibility is not engine capability

A visible accelerator is necessary but not sufficient for accelerated execution.
The current engine may not support its driver/runtime, compute type, operating
system, or device API.

`EngineCapabilityRegistry` keeps that question inside engine-specific providers.
The application planner asks for capabilities by engine name and receives concrete
execution targets such as:

- `cpu:0` with `int8`;
- `cuda:0` with `float16`; or
- `cuda:0` with `int8_float16`.

The planner does not contain NVIDIA, CUDA, Metal, DirectML, ROCm, or OpenVINO policy.
A future engine adapter can advertise different targets without changing the
strategy evaluator.

The first physical accelerator probe uses `nvidia-smi` because faster-whisper's
CTranslate2 runtime can consume CUDA. Discovery is intentionally lightweight and
optional. A missing command, broken driver, timeout, malformed response, or runtime
import failure degrades to a CPU-capable machine instead of preventing EchoFlow from
starting.

CTranslate2 capability inspection is separate from physical discovery. A CUDA
strategy is eligible only when both the physical device and the installed runtime
agree on the exact device and compute type. EchoFlow never treats a detected but
unsupported GPU as useful acceleration.

## Strategy admission

`StrategyDefinition` describes execution placement as well as model quality and cache
cost. A strategy has an engine, model, device, compute type, optional accelerator
backend, system-memory estimate, optional device-memory estimate, quality rank, and
performance rank.

The evaluator remains deterministic. It does not benchmark during planning and does
not use marketing names as hardware heuristics. It asks whether the declared strategy
fits the current evidence.

For dedicated accelerator memory, EchoFlow reserves headroom before admission. The
initial device-memory budget is 80 percent of currently free device memory. This is a
conservative heuristic until representative-machine measurements justify a different
value.

For shared or unified memory, the accelerator requirement is also charged against the
system-memory budget. Unknown memory topology or unknown available device memory fails
closed for strategies that require device memory.

An explicit strategy selection is never silently replaced. If the requested target
is unavailable or no longer safe, EchoFlow returns a typed resource-admission failure.
Automatic selection may fall back to an equally suitable CPU strategy.

## Why pipeline parallelism comes before model sharding

EchoFlow owns media preparation, deterministic segmentation, checkpointing, transcript
assembly, enrichment, and publication. It does not own the tensor graph inside every
speech engine.

Splitting one model between CPU and GPU would couple the application to engine-specific
partitioning behavior, add memory-transfer overhead, complicate packaging, and make
recovery semantics harder to reason about. It may eventually be useful for a specific
engine, but it is not the first optimization boundary.

The first concurrency optimization is therefore bounded pipeline overlap:

1. the accelerator transcribes segment N;
2. one CPU worker may materialize segment N+1 concurrently;
3. the main execution path checkpoints N before it can commit N+1; and
4. at most one unconsumed materialized segment exists.

A prefetch worker is not free. When an accelerated plan has more than one safe CPU
thread, EchoFlow reserves one thread of headroom for segment preparation and gives the
remaining threads to the inference engine. If only one effective CPU thread is
available, accelerated inference may still run, but prefetch depth becomes zero and
materialization remains sequential. EchoFlow does not oversubscribe a CPU quota merely
to claim parallelism.

The same boundedness applies to storage. A CPU plan admits disk for one materialized
segment. An accelerated plan with prefetch enabled admits disk for the current segment
plus one future materialized segment. If prefetch is disabled for lack of CPU
headroom, the storage estimate returns to one segment. Storage admission therefore
matches the maximum temporary files the scheduler can actually own.

There is still one job-scoped inference session and one ordered checkpoint writer.
Prefetch depth is a local scheduling decision, not transcript identity. On resume,
EchoFlow restores the original engine/device/compute contract and can reduce prefetch
depth if the current runner has less spare CPU capacity without invalidating completed
checkpoints.

If future work has not started when a failure occurs, it can be canceled without a
file ever existing. If future materialization has started or completed, its unconsumed
segment is cleaned during unwinding. Cleanup failure does not mask the primary error.
The current segment remains owned by the main execution path and is cleaned there.

This preserves the existing resume invariant: completed checkpoints are a contiguous
prefix of the deterministic segment plan.

## Re-admission and changing machines

Planning is not a permanent reservation of hardware. EchoFlow already rechecks CPU
and system-memory capacity before model initialization. Accelerated execution adds a
fresh accelerator probe and engine-capability check before model load.

A GPU that disappears, loses enough free VRAM, or becomes unsupported after planning
causes a safe refusal. Resume similarly restores the original engine/device/compute
contract and re-admits it against the current machine rather than silently changing
execution placement. Scheduling optimizations such as prefetch can become more
conservative when current CPU headroom shrinks, provided the immutable engine and
checkpoint requirements still fit.

## Benchmarking and calibration

The strategy estimates in this first implementation are deliberately conservative
heuristics. They are not a claim that a particular GPU, laptop, or compute type is
faster than another in sustained use.

Representative-device qualification should measure at least:

- engine/model/device/compute type;
- cold and warm model-cache behavior;
- process-tree peak RSS and CPU usage;
- stage timings, including materialization and inference;
- real-time factor over recordings long enough to expose thermal throttling;
- peak accelerator memory and utilization when the backend exposes those values
  reliably;
- whether one reserved CPU preparation thread improves sustained throughput on the
  target machine; and
- failure/recovery behavior under CPU, RAM, and device-memory contraction.

Those measurements can later drive private local calibration. The planner should
prefer observed evidence over hard-coded hardware-name rules. If measurements show
that overlap is counterproductive on a particular topology, the scheduling layer can
become more conservative without changing canonical transcript semantics.

## Privacy and security

Topology and capability detection are local. EchoFlow does not need to upload hardware
inventory, recordings, transcripts, or benchmark results to choose a strategy.

Accelerator discovery uses fixed argument vectors without a shell. Probe failures are
not allowed to expose arbitrary driver output in routine user-facing errors. Engine
capability checks are read-only and do not authorize model downloads.

The same explicit download authorization and private model-cache boundaries apply to
CPU and accelerated strategies.

## Compatibility rule

The CPU/int8 execution path remains the fallback and the reference compatibility
contract. Future accelerator backends should plug into the same topology, capability,
strategy, observer, checkpoint, and application-runner seams instead of teaching the
CLI or transcription core about hardware brands.

The stable architectural rule is:

> detect resources, negotiate capabilities, admit a concrete strategy, and keep
> checkpoint semantics independent of where inference runs.
