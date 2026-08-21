import { useCallback, useEffect, useMemo, useState } from "react";

import type { DesktopClient, DiscoveredRecording } from "./api/desktop";
import type {
  ExecutionOptions,
  ExportFormat,
  PreflightOptions,
  ProcessingClient,
  ProcessingJob,
  ProcessingModel,
  ProcessingPreflight,
  ProcessingProfile,
  ProcessingReadiness,
  ProcessingTaskStatus,
} from "./api/processing";
import { AudioTrackChooser } from "./components/AudioTrackChooser";
import { WorkspaceHeader, type Theme } from "./components/WorkspaceHeader";

interface ProcessingCenterProps {
  client: DesktopClient;
  processing: ProcessingClient;
  theme: Theme;
  onThemeChange: (theme: Theme) => void;
}

const PROFILE_COPY: Record<
  ProcessingProfile,
  { label: string; detail: string }
> = {
  screening: {
    label: "Quick draft",
    detail: "Fastest locally safe pass. Marked provisional in canonical provenance.",
  },
  balanced: {
    label: "Balanced",
    detail: "Default. EchoFlow chooses the safest quality/performance fit for this machine.",
  },
  accuracy: {
    label: "Best locally safe",
    detail: "Use the highest-quality strategy EchoFlow can admit on this machine.",
  },
};

function basename(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).at(-1) ?? path;
}

function formatBytes(bytes: number): string {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = Math.max(0, bytes);
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value >= 10 || unit === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[unit]}`;
}

function formatDuration(seconds: number): string {
  const rounded = Math.round(seconds);
  const hours = Math.floor(rounded / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  const remainder = rounded % 60;
  return hours > 0
    ? `${hours}h ${minutes}m ${remainder}s`
    : `${minutes}m ${remainder}s`;
}

function progressText(job: ProcessingJob): string {
  if (job.total_segments === null) return "Preparing local work";
  return `${job.completed_segments}/${job.total_segments} segments`;
}

function taskLabel(task: ProcessingTaskStatus | null): string {
  if (!task) return "No supervised task is active.";
  if (task.state === "running") return "Running locally under EchoFlow supervision.";
  if (task.state === "completed") return "Local task completed.";
  if (task.state === "cancelled") return "Local task cancelled. Valid checkpoints remain private.";
  return "Local task stopped before completion. Refresh readiness or job state for details.";
}

function defaultExecutionOptions(): ExecutionOptions {
  return {
    diarize: false,
    allowDiarizationModelDownload: false,
    speakers: null,
    minSpeakers: null,
    maxSpeakers: null,
    exportFormats: ["txt"],
  };
}

export function ProcessingCenter({
  client,
  processing,
  theme,
  onThemeChange,
}: ProcessingCenterProps) {
  const [profile, setProfile] = useState<ProcessingProfile>("balanced");
  const [readiness, setReadiness] = useState<ProcessingReadiness | null>(null);
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [recordings, setRecordings] = useState<DiscoveredRecording[]>([]);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [retrySourceJobId, setRetrySourceJobId] = useState<string | null>(null);
  const [preflight, setPreflight] = useState<ProcessingPreflight | null>(null);
  const [strategyId, setStrategyId] = useState<string | null>(null);
  const [audioStreamIndex, setAudioStreamIndex] = useState<number | null>(null);
  const [enhance, setEnhance] = useState(false);
  const [execution, setExecution] = useState<ExecutionOptions>(defaultExecutionOptions);
  const [task, setTask] = useState<ProcessingTaskStatus | null>(null);
  const [taskDescription, setTaskDescription] = useState<string | null>(null);
  const [pendingRemove, setPendingRemove] = useState<ProcessingModel | null>(null);
  const [pendingDiscard, setPendingDiscard] = useState<ProcessingJob | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(
    "EchoFlow will inspect this machine before it offers a processing path.",
  );
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [nextReadiness, nextJobs] = await Promise.all([
      processing.readiness(profile),
      processing.jobs(),
    ]);
    setReadiness(nextReadiness);
    setJobs(nextJobs);
    try {
      const discovered = await client.discoverRecordings();
      setRecordings(discovered.recordings);
    } catch {
      setRecordings([]);
    }
  }, [client, processing, profile]);

  useEffect(() => {
    setBusy(true);
    setError(null);
    void refresh()
      .catch((caught) => {
        setError(
          caught instanceof Error
            ? caught.message
            : "EchoFlow could not inspect local processing readiness.",
        );
      })
      .finally(() => setBusy(false));
  }, [refresh]);

  useEffect(() => {
    if (!task || task.state !== "running") return undefined;
    const timer = window.setInterval(() => {
      void processing
        .taskStatus(task.task_id)
        .then(async (next) => {
          setTask(next);
          if (next.state !== "running") await refresh();
        })
        .catch(() => undefined);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [processing, refresh, task]);

  const recommendedStrategy = useMemo(
    () => readiness?.strategies.find((strategy) => strategy.recommended) ?? null,
    [readiness],
  );
  const recommendedModel = useMemo(
    () =>
      readiness?.models.find(
        (model) => model.model_id === readiness.recommended_model,
      ) ?? null,
    [readiness],
  );
  const feasibleStrategies = useMemo(
    () => readiness?.strategies.filter((strategy) => strategy.feasible) ?? [],
    [readiness],
  );

  const preflightOptions: PreflightOptions = {
    profile,
    strategyId,
    audioStreamIndex,
    enhance,
  };

  function changeProfile(next: ProcessingProfile) {
    setProfile(next);
    setStrategyId(null);
    setAudioStreamIndex(null);
    setPreflight(null);
    setRetrySourceJobId(null);
    setStatus("Profile changed. EchoFlow is recalculating the safest local path.");
  }

  async function chooseRecording() {
    setError(null);
    const paths = await client.chooseFiles("recording-source");
    const path = paths[0];
    if (!path) return;
    setSelectedPath(path);
    setRetrySourceJobId(null);
    setAudioStreamIndex(null);
    setPreflight(null);
    setStatus(`${basename(path)} selected. Run preflight before starting.`);
  }

  async function planRecording(path = selectedPath) {
    if (!path) return;
    setBusy(true);
    setError(null);
    try {
      const plan = await processing.preflight(path, preflightOptions);
      setPreflight(plan);
      setAudioStreamIndex(
        plan.audio_stream_selection_required ? null : plan.selected_audio_stream_index,
      );
      setRetrySourceJobId(null);
      setStatus(
        plan.audio_stream_selection_required
          ? `Preflight found ${plan.audio_streams.length} audio tracks. Choose the track EchoFlow should transcribe.`
          : `Preflight complete. EchoFlow admitted ${plan.model} on ${plan.device}/${plan.compute_type}.`,
      );
    } catch (caught) {
      setPreflight(null);
      setError(
        caught instanceof Error
          ? caught.message
          : "EchoFlow could not safely plan this recording.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function prepareRetry(
    job: ProcessingJob,
    requestedAudioStreamIndex = audioStreamIndex,
  ) {
    setBusy(true);
    setError(null);
    try {
      const plan = await processing.retryPreflight(job.job_id, {
        ...preflightOptions,
        audioStreamIndex: requestedAudioStreamIndex,
      });
      setPreflight(plan);
      setSelectedPath(null);
      setRetrySourceJobId(job.job_id);
      setAudioStreamIndex(
        plan.audio_stream_selection_required ? null : plan.selected_audio_stream_index,
      );
      setStatus(
        plan.audio_stream_selection_required
          ? `Fresh retry preflight found ${plan.audio_streams.length} audio tracks. Choose the track EchoFlow should transcribe.`
          : `Fresh retry preflight complete for ${job.recording_name}. The interrupted job was not changed.`,
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "EchoFlow could not plan a fresh retry.");
    } finally {
      setBusy(false);
    }
  }

  async function chooseAudioStream(index: number) {
    if (!preflight) return;
    if (!selectedPath && !retrySourceJobId) return;
    setBusy(true);
    setError(null);
    const previousIndex = audioStreamIndex;
    setAudioStreamIndex(index);
    try {
      const options = { ...preflightOptions, audioStreamIndex: index };
      const plan = retrySourceJobId
        ? await processing.retryPreflight(retrySourceJobId, options)
        : await processing.preflight(selectedPath ?? "", options);
      setPreflight(plan);
      setAudioStreamIndex(plan.selected_audio_stream_index);
      setStatus(
        `Audio track #${plan.selected_audio_stream_index} confirmed. EchoFlow re-ran backend preflight with that exact stream.`,
      );
    } catch (caught) {
      setAudioStreamIndex(previousIndex);
      setError(
        caught instanceof Error
          ? caught.message
          : "EchoFlow could not safely bind that audio track.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function startPlannedJob() {
    if (!preflight || preflight.audio_stream_selection_required) return;
    if (!retrySourceJobId && !selectedPath) return;
    setBusy(true);
    setError(null);
    try {
      const started = retrySourceJobId
        ? await processing.retryTranscription(
            retrySourceJobId,
            preflight,
            preflightOptions,
            execution,
          )
        : await processing.startTranscription(
            selectedPath ?? "",
            preflight,
            preflightOptions,
            execution,
          );
      setTask(started);
      setTaskDescription(`Transcribing ${preflight.recording_name}`);
      setStatus(
        "Transcription launched as a supervised local process. Closing the browser view does not turn it into a browser request.",
      );
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "EchoFlow could not launch this local job.");
    } finally {
      setBusy(false);
    }
  }

  async function resumeJob(job: ProcessingJob) {
    setBusy(true);
    setError(null);
    try {
      const started = await processing.resumeTranscription(job, execution);
      setTask(started);
      setTaskDescription(`Resuming ${job.recording_name}`);
      setStatus(
        "Resume launched. Python restored the checkpointed execution contract and re-admitted current hardware before continuing.",
      );
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "EchoFlow could not resume this job safely.");
    } finally {
      setBusy(false);
    }
  }

  async function installModel(model: ProcessingModel) {
    setBusy(true);
    setError(null);
    try {
      const started = await processing.installModel(model.model_id);
      setTask(started);
      setTaskDescription(`Installing verified ${model.model_id} model`);
      setStatus(
        `Model acquisition started locally. EchoFlow will not register ${model.model_id} until the snapshot passes verification.`,
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "EchoFlow could not start model installation.");
    } finally {
      setBusy(false);
    }
  }

  async function removeModel(model: ProcessingModel) {
    setBusy(true);
    setError(null);
    try {
      const started = await processing.removeModel(model);
      setTask(started);
      setTaskDescription(`Removing ${model.model_id} model`);
      setPendingRemove(null);
      setStatus(
        "Model removal started. The expected verified revision is bound to this request; changed model state will be rejected.",
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "EchoFlow could not remove that model safely.");
    } finally {
      setBusy(false);
    }
  }

  async function verifyModel(model: ProcessingModel) {
    setBusy(true);
    setError(null);
    try {
      const verified = await processing.verifyModel(model.model_id);
      setStatus(
        verified.installed
          ? `${model.model_id} is still a verified EchoFlow-managed revision.`
          : `${model.model_id} is not currently installed under EchoFlow custody.`,
      );
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "EchoFlow could not verify that model.");
    } finally {
      setBusy(false);
    }
  }

  async function discardJob(job: ProcessingJob) {
    setBusy(true);
    setError(null);
    try {
      await processing.discardJob(job);
      setPendingDiscard(null);
      setStatus(
        "Private checkpoint and lifecycle state discarded. Published transcript evidence was not part of that operation.",
      );
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "EchoFlow could not discard that private state.");
    } finally {
      setBusy(false);
    }
  }

  async function cancelTask() {
    if (!task || task.state !== "running") return;
    setBusy(true);
    setError(null);
    try {
      const cancelled = await processing.cancelTask(task.task_id);
      setTask(cancelled);
      setStatus(
        "Local task cancelled. A transcription job will reconcile to interrupted state and preserve valid checkpoints on refresh.",
      );
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "EchoFlow could not cancel that local task.");
    } finally {
      setBusy(false);
    }
  }

  function toggleExport(format: ExportFormat) {
    setExecution((current) => {
      const selected = new Set(current.exportFormats);
      if (selected.has(format)) selected.delete(format);
      else selected.add(format);
      return { ...current, exportFormats: [...selected] };
    });
  }

  return (
    <>
      <WorkspaceHeader
        eyebrow="Processing center"
        title="Turn recordings into durable evidence."
        theme={theme}
        onThemeChange={onThemeChange}
      />

      <section className="processing-intro" aria-labelledby="processing-title">
        <div>
          <p className="section-kicker">02 · Plan, admit, run, recover</p>
          <h2 id="processing-title">EchoFlow chooses a safe local path before it spends your machine.</h2>
        </div>
        <p>
          Machine limits, model custody, transcription planning, and checkpoint recovery stay in Python. Tauri supervises long work. This screen only presents and submits your intent.
        </p>
      </section>

      <div className="processing-status" aria-live="polite">
        <p role="status">{status}</p>
        {error && <p className="error-banner" role="alert">{error}</p>}
      </div>

      <section className="processing-grid" aria-label="Processing readiness">
        <article className="processing-card readiness-card">
          <div className="processing-card-heading">
            <div>
              <p className="mini-label">Machine readiness</p>
              <h3>{readiness ? readiness.health.status : "Inspecting…"}</h3>
            </div>
            <button type="button" className="secondary-action" onClick={() => void refresh()} disabled={busy}>
              Refresh
            </button>
          </div>
          {readiness && (
            <>
              <dl className="processing-metrics">
                <div><dt>Effective CPU</dt><dd>{readiness.resources.effective_cpus} threads visible</dd></div>
                <div><dt>Available memory</dt><dd>{formatBytes(readiness.resources.effective_memory_available_bytes)}</dd></div>
                <div><dt>Safe memory budget</dt><dd>{formatBytes(readiness.policy.memory_budget_bytes)}</dd></div>
              </dl>
              <ul className="readiness-checks" aria-label="Local health checks">
                {readiness.health.checks.map((check) => (
                  <li key={check.check_id} data-status={check.status}>
                    <span className="health-dot" aria-hidden="true" />
                    <span><strong>{check.summary}</strong><small>{check.required ? "Required" : "Advisory"}</small></span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </article>

        <article className="processing-card profile-card">
          <p className="mini-label">Processing intent</p>
          <h3>Tell EchoFlow the outcome, not the thread count.</h3>
          <fieldset className="profile-options">
            <legend>Processing profile</legend>
            {(Object.keys(PROFILE_COPY) as ProcessingProfile[]).map((value) => (
              <label key={value} className={profile === value ? "profile-option profile-option-active" : "profile-option"}>
                <input
                  type="radio"
                  name="processing-profile"
                  value={value}
                  checked={profile === value}
                  onChange={() => changeProfile(value)}
                />
                <span><strong>{PROFILE_COPY[value].label}</strong><small>{PROFILE_COPY[value].detail}</small></span>
              </label>
            ))}
          </fieldset>
          {recommendedStrategy && (
            <p className="backend-choice" aria-label="EchoFlow recommendation">
              <strong>EchoFlow currently recommends:</strong> {recommendedStrategy.model} · {recommendedStrategy.device}/{recommendedStrategy.compute_type}
            </p>
          )}
        </article>
      </section>

      <section className="processing-card models-card" aria-labelledby="models-title">
        <div className="processing-card-heading">
          <div>
            <p className="mini-label">Local model custody</p>
            <h3 id="models-title">Verified models, explicit downloads.</h3>
          </div>
          {recommendedModel && (
            <span className={readiness?.recommended_model_installed ? "model-ready" : "model-needed"}>
              {readiness?.recommended_model_installed ? "Recommended model ready" : "Recommended model needed"}
            </span>
          )}
        </div>
        <div className="model-list">
          {readiness?.models.map((model) => (
            <article key={model.model_id} className="model-row">
              <div>
                <strong>{model.model_id}</strong>
                <span>{model.installed ? `Verified · ${formatBytes(model.installed_size_bytes ?? model.estimated_cache_bytes)}` : `Download cost about ${formatBytes(model.estimated_cache_bytes)}`}</span>
              </div>
              <div className="model-actions">
                {model.installed ? (
                  <>
                    <button type="button" onClick={() => void verifyModel(model)} disabled={busy}>Revalidate</button>
                    <button type="button" className="danger-link" onClick={() => setPendingRemove(model)} disabled={busy}>Remove</button>
                  </>
                ) : (
                  <button type="button" className="secondary-action" onClick={() => void installModel(model)} disabled={busy}>Install explicitly</button>
                )}
              </div>
            </article>
          ))}
        </div>
        {pendingRemove && (
          <div className="confirmation-panel" aria-label={`Remove ${pendingRemove.model_id} confirmation`}>
            <p>
              Remove EchoFlow's managed <strong>{pendingRemove.model_id}</strong> revision from the local model cache? Transcript evidence and recordings are not part of this operation.
            </p>
            <div>
              <button type="button" onClick={() => setPendingRemove(null)}>Keep model</button>
              <button type="button" className="danger-action" onClick={() => void removeModel(pendingRemove)}>Remove verified revision</button>
            </div>
          </div>
        )}
      </section>

      <section className="processing-card plan-card" aria-labelledby="preflight-title">
        <div className="processing-card-heading">
          <div>
            <p className="mini-label">Transcription preflight</p>
            <h3 id="preflight-title">Review the plan before EchoFlow starts.</h3>
          </div>
          <button type="button" className="secondary-action" onClick={() => void chooseRecording()} disabled={busy}>
            Choose recording
          </button>
        </div>

        {recordings.length > 0 && (
          <div className="recording-choices" role="group" aria-label="Discovered recordings">
            {recordings.slice(0, 6).map((recording) => (
              <button
                type="button"
                key={recording.path}
                className={selectedPath === recording.path ? "recording-choice recording-choice-active" : "recording-choice"}
                onClick={() => {
                  setSelectedPath(recording.path);
                  setRetrySourceJobId(null);
                  setAudioStreamIndex(null);
                  setPreflight(null);
                }}
              >
                <strong>{basename(recording.path)}</strong>
                <span>{formatBytes(recording.size_bytes)}</span>
              </button>
            ))}
          </div>
        )}

        <div className="preflight-selection">
          <div>
            <span className="mini-label">Selected recording</span>
            <strong>{preflight?.recording_name ?? (selectedPath ? basename(selectedPath) : "None yet")}</strong>
          </div>
          <button
            type="button"
            className="primary-action"
            disabled={busy || (!selectedPath && !retrySourceJobId)}
            onClick={() => retrySourceJobId ? void prepareRetry(jobs.find((job) => job.job_id === retrySourceJobId) ?? jobs[0]!) : void planRecording()}
          >
            {busy ? "Checking…" : preflight ? "Re-run preflight" : "Run preflight"}
          </button>
        </div>

        {preflight && (
          <div className="preflight-result" aria-label="Backend transcription preflight">
            <div className="preflight-hero">
              <div>
                <span className="mini-label">Admitted by EchoFlow</span>
                <strong>{PROFILE_COPY[preflight.profile].label} · {preflight.model}</strong>
                <p>{preflight.engine} · {preflight.device}/{preflight.compute_type} · {preflight.decode_strategy}</p>
              </div>
              <span className={preflight.fits_memory_budget ? "plan-safe" : "plan-blocked"}>
                {preflight.fits_memory_budget ? "Fits safe budget" : "Blocked"}
              </span>
            </div>
            <dl className="processing-metrics preflight-metrics">
              <div><dt>Duration</dt><dd>{formatDuration(preflight.duration_seconds)}</dd></div>
              <div><dt>Peak memory estimate</dt><dd>{formatBytes(preflight.estimated_peak_memory_bytes)}</dd></div>
              <div><dt>Disk estimate</dt><dd>{formatBytes(preflight.estimated_disk_bytes)}</dd></div>
              <div><dt>Audio stream</dt><dd>#{preflight.selected_audio_stream_index}</dd></div>
            </dl>
            <AudioTrackChooser
              streams={preflight.audio_streams}
              selectedIndex={audioStreamIndex}
              selectionRequired={preflight.audio_stream_selection_required}
              busy={busy}
              onSelect={(index) => void chooseAudioStream(index)}
            />
            <details className="advanced-card processing-advanced">
              <summary>Expert controls and optional processing</summary>
              <div className="advanced-processing-grid">
                <label>
                  <span>Safe strategy override</span>
                  <select
                    value={strategyId ?? ""}
                    onChange={(event) => {
                      setStrategyId(event.target.value || null);
                      setPreflight(null);
                    }}
                  >
                    <option value="">Automatic recommendation</option>
                    {feasibleStrategies.map((strategy) => (
                      <option key={strategy.strategy_id} value={strategy.strategy_id}>{strategy.strategy_id}</option>
                    ))}
                  </select>
                </label>
              </div>
              <label className="checkbox-row">
                <input type="checkbox" checked={enhance} onChange={(event) => { setEnhance(event.target.checked); setPreflight(null); }} />
                <span><strong>Deterministic noise suppression</strong><small>Changes the planned audio preprocessing contract and requires a new preflight.</small></span>
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={execution.diarize}
                  onChange={(event) => setExecution((current) => ({ ...current, diarize: event.target.checked, allowDiarizationModelDownload: event.target.checked ? current.allowDiarizationModelDownload : false }))}
                />
                <span><strong>Anonymous local speaker labeling</strong><small>Optional post-ASR diarization. Speaker identities remain recording-scoped labels.</small></span>
              </label>
              {execution.diarize && (
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={execution.allowDiarizationModelDownload}
                    onChange={(event) => setExecution((current) => ({ ...current, allowDiarizationModelDownload: event.target.checked }))}
                  />
                  <span><strong>Allow diarization model acquisition if missing</strong><small>Separate explicit network consent. Transcription model downloads are never implied by Start.</small></span>
                </label>
              )}
              <fieldset className="export-options">
                <legend>Derived publication after canonical JSON succeeds</legend>
                {(["txt", "srt", "vtt"] as ExportFormat[]).map((format) => (
                  <label key={format}><input type="checkbox" checked={execution.exportFormats.includes(format)} onChange={() => toggleExport(format)} />{format.toUpperCase()}</label>
                ))}
              </fieldset>
            </details>
            <div className="launch-row">
              <p>
                {preflight.audio_stream_selection_required
                  ? "Choose an audio track above before starting. EchoFlow will not treat the container's first track as user intent."
                  : "Start re-runs backend admission immediately before execution. A changed machine, model, source, or strategy fails closed instead of trusting this displayed plan."}
              </p>
              <button
                type="button"
                className="primary-action"
                disabled={
                  busy ||
                  !preflight.fits_memory_budget ||
                  preflight.audio_stream_selection_required
                }
                onClick={() => void startPlannedJob()}
              >
                Start local transcription
              </button>
            </div>
          </div>
        )}
      </section>

      {task && (
        <section className="processing-card task-card" aria-label="Supervised local task">
          <div>
            <p className="mini-label">Native task supervisor</p>
            <h3>{taskDescription ?? "Local processing task"}</h3>
            <p role="status">{taskLabel(task)}</p>
          </div>
          <div className="task-actions">
            <button type="button" onClick={() => void processing.taskStatus(task.task_id).then(setTask)}>Refresh task</button>
            {task.state === "running" && <button type="button" className="danger-link" onClick={() => void cancelTask()}>Cancel local task</button>}
          </div>
        </section>
      )}

      <section className="processing-card jobs-card" aria-labelledby="jobs-title">
        <div className="processing-card-heading">
          <div>
            <p className="mini-label">Private job lifecycle</p>
            <h3 id="jobs-title">Recover work without guessing what survived.</h3>
          </div>
          <button type="button" className="secondary-action" onClick={() => void refresh()} disabled={busy}>Refresh jobs</button>
        </div>
        <div className="job-list">
          {jobs.length === 0 && <p className="empty-state">No local transcription jobs yet.</p>}
          {jobs.map((job) => (
            <article key={job.job_id} className="job-row">
              <div className="job-main">
                <div>
                  <strong>{job.recording_name}</strong>
                  <span>{job.status} · {progressText(job)}</span>
                </div>
                {job.total_segments !== null && (
                  <progress value={job.completed_segments} max={Math.max(1, job.total_segments)} aria-label={`${job.recording_name} progress`} />
                )}
                {job.failure_message && <p className="failure-copy">{job.failure_message}</p>}
              </div>
              <div className="job-actions">
                {job.resumable && job.status !== "running" && (
                  <button type="button" className="primary-action compact-action" onClick={() => void resumeJob(job)}>Resume checkpoint</button>
                )}
                {job.status !== "running" && (
                  <button type="button" onClick={() => void prepareRetry(job, null)}>Plan fresh retry</button>
                )}
                {job.status !== "running" && (
                  <button type="button" className="danger-link" onClick={() => setPendingDiscard(job)}>Discard private state</button>
                )}
              </div>
            </article>
          ))}
        </div>
        {pendingDiscard && (
          <div className="confirmation-panel" aria-label={`Discard ${pendingDiscard.recording_name} job confirmation`}>
            <p>
              Discard private checkpoints and lifecycle state for <strong>{pendingDiscard.recording_name}</strong>? Published transcript artifacts, canonical evidence, research notes, and the original recording are not part of this operation.
            </p>
            <div>
              <button type="button" onClick={() => setPendingDiscard(null)}>Keep state</button>
              <button type="button" className="danger-action" onClick={() => void discardJob(pendingDiscard)}>Discard private state</button>
            </div>
          </div>
        )}
      </section>
    </>
  );
}
