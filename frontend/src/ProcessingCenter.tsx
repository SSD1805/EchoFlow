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
    detail: "Fastest option for a first pass. The resulting transcript is marked as a draft.",
  },
  balanced: {
    label: "Balanced",
    detail: "Recommended for most recordings. Balances speed and transcription quality for this computer.",
  },
  accuracy: {
    label: "Best quality",
    detail: "Prioritize transcription quality using the strongest option this computer can run safely.",
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
  if (job.total_segments === null) return "Preparing";
  return `${job.completed_segments}/${job.total_segments} sections`;
}

function taskLabel(task: ProcessingTaskStatus | null): string {
  if (!task) return "No task is running.";
  if (task.state === "running") return "Running on this computer.";
  if (task.state === "completed") return "Completed.";
  if (task.state === "cancelled") return "Cancelled. Resumable progress was kept when possible.";
  return "Stopped before completion. Refresh to see whether it can be resumed.";
}

function readinessLabel(status: ProcessingReadiness["health"]["status"]): string {
  if (status === "healthy") return "Ready";
  if (status === "degraded") return "Needs attention";
  return "Not ready";
}

function deviceLabel(device: string): string {
  if (device === "cuda") return "NVIDIA GPU";
  if (device === "cpu") return "CPU";
  return device.toUpperCase();
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
    "Checking this computer so Scholion can choose transcription settings that will run safely.",
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
            : "Scholion could not check this computer for local transcription.",
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
    setStatus("Transcription preference changed. Scholion is checking the best local setup again.");
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
    setStatus(`${basename(path)} selected. Check the recording before starting.`);
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
          ? `Found ${plan.audio_streams.length} audio tracks. Choose the one you want to transcribe.`
          : `Ready to transcribe ${plan.recording_name} with the ${plan.model} model using ${deviceLabel(plan.device)}.`,
      );
    } catch (caught) {
      setPreflight(null);
      setError(
        caught instanceof Error
          ? caught.message
          : "Scholion could not prepare this recording for transcription.",
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
          ? `Found ${plan.audio_streams.length} audio tracks. Choose the one you want to transcribe.`
          : `A fresh retry is ready for ${job.recording_name}. The earlier job has not been changed.`,
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Scholion could not prepare a fresh retry.");
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
      setStatus(`Audio track #${plan.selected_audio_stream_index} selected.`);
    } catch (caught) {
      setAudioStreamIndex(previousIndex);
      setError(
        caught instanceof Error
          ? caught.message
          : "Scholion could not use that audio track.",
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
      setStatus("Transcription started on this computer.");
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Scholion could not start this transcription.");
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
      setStatus(`Resuming ${job.recording_name} from saved progress.`);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Scholion could not resume this job.");
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
      setTaskDescription(`Downloading ${model.model_id} transcription model`);
      setStatus(`Downloading the ${model.model_id} transcription model to this device. Scholion will check it before using it.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Scholion could not start the model download.");
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
      setTaskDescription(`Removing ${model.model_id} transcription model`);
      setPendingRemove(null);
      setStatus(`Removing the ${model.model_id} transcription model from this device.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Scholion could not remove that model.");
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
          ? `The ${model.model_id} transcription model is ready to use.`
          : `The ${model.model_id} transcription model is not installed.`,
      );
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Scholion could not check that model.");
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
      setStatus("Temporary processing files were removed. Your recording and finished transcripts were left alone.");
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Scholion could not remove those temporary files.");
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
      setStatus("Transcription stopped. Resumable progress was kept when possible.");
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Scholion could not stop that task.");
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
        title="Transcribe recordings."
        theme={theme}
        onThemeChange={onThemeChange}
      />

      <section className="processing-intro" aria-labelledby="processing-title">
        <div>
          <p className="section-kicker">02 · Transcribe</p>
          <h2 id="processing-title">Choose a recording and review the setup.</h2>
        </div>
        <p>
          Scholion checks this computer so it can choose transcription settings that fit the available memory and hardware. This check stays on this device. Scholion does not send hardware information or telemetry anywhere.
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
              <p className="mini-label">This computer</p>
              <h3>{readiness ? readinessLabel(readiness.health.status) : "Checking…"}</h3>
            </div>
            <button type="button" className="secondary-action" onClick={() => void refresh()} disabled={busy}>
              Check again
            </button>
          </div>
          {readiness && (
            <>
              <dl className="processing-metrics">
                <div>
                  <dt>Processor</dt>
                  <dd>{readiness.resources.processor_name ?? readiness.resources.machine}</dd>
                  <small>{readiness.resources.effective_cpus} threads available</small>
                </div>
                <div>
                  <dt>Memory</dt>
                  <dd>{formatBytes(readiness.resources.memory_available_bytes)} available</dd>
                  <small>{formatBytes(readiness.resources.memory_total_bytes)} installed</small>
                </div>
                {readiness.resources.accelerators.length > 0 ? (
                  readiness.resources.accelerators.map((accelerator) => (
                    <div key={accelerator.accelerator_id}>
                      <dt>Graphics</dt>
                      <dd>{accelerator.name}</dd>
                      <small>
                        {accelerator.memory_available_bytes !== null
                          ? `${formatBytes(accelerator.memory_available_bytes)} graphics memory available`
                          : "Graphics memory availability unknown"}
                      </small>
                    </div>
                  ))
                ) : (
                  <div><dt>Graphics</dt><dd>No supported accelerator detected</dd></div>
                )}
              </dl>
              <details className="advanced-card processing-advanced">
                <summary>How Scholion chose these limits</summary>
                <p>
                  Scholion currently reserves part of the available memory and will use at most {formatBytes(readiness.policy.memory_budget_bytes)} for this transcription setup.
                </p>
                <ul className="readiness-checks" aria-label="Local health checks">
                  {readiness.health.checks.map((check) => (
                    <li key={check.check_id} data-status={check.status}>
                      <span className="health-dot" aria-hidden="true" />
                      <span><strong>{check.summary}</strong><small>{check.required ? "Required" : "Optional"}</small></span>
                    </li>
                  ))}
                </ul>
              </details>
            </>
          )}
        </article>

        <article className="processing-card profile-card">
          <p className="mini-label">Transcription preference</p>
          <h3>Choose what matters most for this recording.</h3>
          <fieldset className="profile-options">
            <legend>Transcription style</legend>
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
            <p className="backend-choice" aria-label="Scholion recommendation">
              <strong>Recommended setup:</strong> {recommendedStrategy.model} model · {deviceLabel(recommendedStrategy.device)}
            </p>
          )}
        </article>
      </section>

      <section className="processing-card models-card" aria-labelledby="models-title">
        <div className="processing-card-heading">
          <div>
            <p className="mini-label">Transcription models</p>
            <h3 id="models-title">Models used for local transcription.</h3>
          </div>
          {recommendedModel && (
            <span className={readiness?.recommended_model_installed ? "model-ready" : "model-needed"}>
              {readiness?.recommended_model_installed ? "Recommended model installed" : "Recommended model needs download"}
            </span>
          )}
        </div>
        <p>Models are downloaded only when you choose. Once installed, transcription can run without an internet connection.</p>
        <div className="model-list">
          {readiness?.models.map((model) => (
            <article key={model.model_id} className="model-row">
              <div>
                <strong>{model.model_id}</strong>
                <span>{model.installed ? `Installed · ${formatBytes(model.installed_size_bytes ?? model.estimated_cache_bytes)}` : `Download size about ${formatBytes(model.estimated_cache_bytes)}`}</span>
              </div>
              <div className="model-actions">
                {model.installed ? (
                  <>
                    <button type="button" onClick={() => void verifyModel(model)} disabled={busy}>Check files</button>
                    <button type="button" className="danger-link" onClick={() => setPendingRemove(model)} disabled={busy}>Remove</button>
                  </>
                ) : (
                  <button type="button" className="secondary-action" onClick={() => void installModel(model)} disabled={busy}>Download model</button>
                )}
              </div>
            </article>
          ))}
        </div>
        {pendingRemove && (
          <div className="confirmation-panel" aria-label={`Remove ${pendingRemove.model_id} confirmation`}>
            <p>
              Remove the <strong>{pendingRemove.model_id}</strong> transcription model from this device? Recordings and transcripts will not be deleted.
            </p>
            <div>
              <button type="button" onClick={() => setPendingRemove(null)}>Keep model</button>
              <button type="button" className="danger-action" onClick={() => void removeModel(pendingRemove)}>Remove model</button>
            </div>
          </div>
        )}
      </section>

      <section className="processing-card plan-card" aria-labelledby="preflight-title">
        <div className="processing-card-heading">
          <div>
            <p className="mini-label">Recording setup</p>
            <h3 id="preflight-title">Review before starting.</h3>
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
            {busy ? "Checking…" : preflight ? "Check again" : "Check recording"}
          </button>
        </div>

        {preflight && (
          <div className="preflight-result" aria-label="Transcription setup">
            <div className="preflight-hero">
              <div>
                <span className="mini-label">Ready to transcribe</span>
                <strong>{PROFILE_COPY[preflight.profile].label} · {preflight.model}</strong>
                <p>{deviceLabel(preflight.device)} · {formatDuration(preflight.duration_seconds)}</p>
              </div>
              <span className={preflight.fits_memory_budget ? "plan-safe" : "plan-blocked"}>
                {preflight.fits_memory_budget ? "Ready" : "Cannot run safely"}
              </span>
            </div>
            <dl className="processing-metrics preflight-metrics">
              <div><dt>Duration</dt><dd>{formatDuration(preflight.duration_seconds)}</dd></div>
              <div><dt>Estimated memory use</dt><dd>{formatBytes(preflight.estimated_peak_memory_bytes)}</dd></div>
              <div><dt>Temporary disk space</dt><dd>{formatBytes(preflight.estimated_disk_bytes)}</dd></div>
              <div><dt>Audio track</dt><dd>#{preflight.selected_audio_stream_index}</dd></div>
            </dl>
            <AudioTrackChooser
              streams={preflight.audio_streams}
              selectedIndex={audioStreamIndex}
              selectionRequired={preflight.audio_stream_selection_required}
              busy={busy}
              onSelect={(index) => void chooseAudioStream(index)}
            />
            <details className="advanced-card processing-advanced">
              <summary>Advanced options</summary>
              <div className="advanced-processing-grid">
                <label>
                  <span>Processing method</span>
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
                <span><strong>Reduce steady background noise</strong><small>Applies local noise reduction before transcription. Changing this setting requires another recording check.</small></span>
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={execution.diarize}
                  onChange={(event) => setExecution((current) => ({ ...current, diarize: event.target.checked, allowDiarizationModelDownload: event.target.checked ? current.allowDiarizationModelDownload : false }))}
                />
                <span><strong>Label speakers automatically</strong><small>Adds recording-specific labels such as Speaker 1 and Speaker 2 after transcription.</small></span>
              </label>
              {execution.diarize && (
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={execution.allowDiarizationModelDownload}
                    onChange={(event) => setExecution((current) => ({ ...current, allowDiarizationModelDownload: event.target.checked }))}
                  />
                  <span><strong>Download the speaker-labeling model if needed</strong><small>This is a separate download and only happens when you enable it.</small></span>
                </label>
              )}
              <fieldset className="export-options">
                <legend>Create extra copies after the Scholion transcript is saved</legend>
                {(["txt", "srt", "vtt"] as ExportFormat[]).map((format) => (
                  <label key={format}><input type="checkbox" checked={execution.exportFormats.includes(format)} onChange={() => toggleExport(format)} />{format.toUpperCase()}</label>
                ))}
              </fieldset>
            </details>
            <div className="launch-row">
              <p>
                {preflight.audio_stream_selection_required
                  ? "Choose an audio track above before starting."
                  : "Scholion checks the recording and current machine resources once more when you start."}
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
                Start transcription
              </button>
            </div>
          </div>
        )}
      </section>

      {task && (
        <section className="processing-card task-card" aria-label="Current local task">
          <div>
            <p className="mini-label">Current task</p>
            <h3>{taskDescription ?? "Local processing task"}</h3>
            <p role="status">{taskLabel(task)}</p>
          </div>
          <div className="task-actions">
            <button type="button" onClick={() => void processing.taskStatus(task.task_id).then(setTask)}>Refresh</button>
            {task.state === "running" && <button type="button" className="danger-link" onClick={() => void cancelTask()}>Stop</button>}
          </div>
        </section>
      )}

      <section className="processing-card jobs-card" aria-labelledby="jobs-title">
        <div className="processing-card-heading">
          <div>
            <p className="mini-label">Previous transcription jobs</p>
            <h3 id="jobs-title">Resume or retry unfinished work.</h3>
          </div>
          <button type="button" className="secondary-action" onClick={() => void refresh()} disabled={busy}>Refresh</button>
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
                  <button type="button" className="primary-action compact-action" onClick={() => void resumeJob(job)}>Resume</button>
                )}
                {job.status !== "running" && (
                  <button type="button" onClick={() => void prepareRetry(job, null)}>Retry from beginning</button>
                )}
                {job.status !== "running" && (
                  <button type="button" className="danger-link" onClick={() => setPendingDiscard(job)}>Remove temporary files</button>
                )}
              </div>
            </article>
          ))}
        </div>
        {pendingDiscard && (
          <div className="confirmation-panel" aria-label={`Remove temporary files for ${pendingDiscard.recording_name}`}>
            <p>
              Remove saved progress and temporary processing files for <strong>{pendingDiscard.recording_name}</strong>? The original recording and any finished transcripts will stay in place.
            </p>
            <div>
              <button type="button" onClick={() => setPendingDiscard(null)}>Keep files</button>
              <button type="button" className="danger-action" onClick={() => void discardJob(pendingDiscard)}>Remove temporary files</button>
            </div>
          </div>
        )}
      </section>
    </>
  );
}
