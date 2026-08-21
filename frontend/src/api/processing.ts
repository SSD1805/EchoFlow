export type ProcessingProfile = "screening" | "balanced" | "accuracy";
export type ExportFormat = "txt" | "srt" | "vtt";

export interface ProcessingHealthCheck {
  check_id: string;
  status: "pass" | "warn" | "fail";
  summary: string;
  required: boolean;
  error_code: string | null;
}

export interface ProcessingStrategy {
  strategy_id: string;
  model: string;
  device: string;
  compute_type: string;
  estimated_peak_memory_bytes: number;
  estimated_peak_device_memory_bytes: number;
  model_cache_bytes: number;
  feasible: boolean;
  rejection_reasons: string[];
  recommended: boolean;
}

export interface ProcessingModel {
  model_id: string;
  engine: string;
  estimated_cache_bytes: number;
  quality_rank: number;
  installed: boolean;
  resolved_revision: string | null;
  installed_size_bytes: number | null;
  verification: string | null;
}

export interface ProcessingReadiness {
  health: {
    status: "healthy" | "degraded" | "unhealthy";
    checks: ProcessingHealthCheck[];
  };
  resources: {
    platform: string;
    machine: string;
    effective_cpus: number;
    effective_memory_available_bytes: number;
    constraints: string[];
  };
  policy: {
    profile: ProcessingProfile;
    provisional: boolean;
    cpu_threads: number;
    memory_budget_bytes: number;
    constraints: string[];
  };
  strategies: ProcessingStrategy[];
  models: ProcessingModel[];
  recommended_model: string | null;
  recommended_model_installed: boolean;
}

export interface ProcessingJob {
  job_id: string;
  recording_name: string;
  status: "running" | "interrupted" | "failed" | "completed";
  started_at: string;
  updated_at: string;
  total_segments: number | null;
  completed_segments: number;
  progress_fraction: number | null;
  resumable: boolean;
  artifact_published: boolean;
  error_code: string | null;
  failure_message: string | null;
}

export interface ProcessingAudioStream {
  index: number;
  codec: string;
  duration_seconds: number | null;
  sample_rate_hz: number | null;
  channels: number | null;
  title: string | null;
  language: string | null;
  is_default: boolean;
}

export interface ProcessingPreflight {
  job_id: string;
  recording_name: string;
  source_sha256: string;
  container_format: string;
  duration_seconds: number;
  audio_streams: ProcessingAudioStream[];
  selected_audio_stream_index: number;
  audio_stream_selection_required: boolean;
  profile: ProcessingProfile;
  provisional: boolean;
  strategy_id: string;
  engine: string;
  model: string;
  model_revision: string;
  device: string;
  compute_type: string;
  cpu_threads: number;
  decode_strategy: string;
  enhancement_enabled: boolean;
  estimated_disk_bytes: number;
  estimated_peak_memory_bytes: number;
  memory_budget_bytes: number;
  fits_memory_budget: boolean;
  warnings: string[];
}

export interface ProcessingTaskStatus {
  task_id: string;
  state: "running" | "completed" | "failed" | "cancelled";
  exit_code: number | null;
}

export interface PreflightOptions {
  profile: ProcessingProfile;
  strategyId?: string | null;
  audioStreamIndex?: number | null;
  enhance?: boolean;
}

export interface ExecutionOptions {
  diarize: boolean;
  allowDiarizationModelDownload: boolean;
  speakers: number | null;
  minSpeakers: number | null;
  maxSpeakers: number | null;
  exportFormats: ExportFormat[];
}

export interface ProcessingClient {
  readiness(profile: ProcessingProfile): Promise<ProcessingReadiness>;
  jobs(): Promise<ProcessingJob[]>;
  preflight(inputPath: string, options: PreflightOptions): Promise<ProcessingPreflight>;
  retryPreflight(sourceJobId: string, options: PreflightOptions): Promise<ProcessingPreflight>;
  discardJob(job: ProcessingJob): Promise<void>;
  verifyModel(modelId: string): Promise<{ model_id: string; installed: boolean; resolved_revision: string | null }>;
  startTranscription(
    inputPath: string,
    plan: ProcessingPreflight,
    options: PreflightOptions,
    execution: ExecutionOptions,
  ): Promise<ProcessingTaskStatus>;
  retryTranscription(
    sourceJobId: string,
    plan: ProcessingPreflight,
    options: PreflightOptions,
    execution: ExecutionOptions,
  ): Promise<ProcessingTaskStatus>;
  resumeTranscription(
    job: ProcessingJob,
    execution: ExecutionOptions,
  ): Promise<ProcessingTaskStatus>;
  installModel(modelId: string, revision?: string | null): Promise<ProcessingTaskStatus>;
  removeModel(model: ProcessingModel): Promise<ProcessingTaskStatus>;
  taskStatus(taskId: string): Promise<ProcessingTaskStatus>;
  cancelTask(taskId: string): Promise<ProcessingTaskStatus>;
}

interface DesktopError {
  code: string;
  message: string;
}

interface DesktopResponse<T> {
  protocol_version: 1;
  request_id: string;
  ok: boolean;
  result: T | null;
  error: DesktopError | null;
}

function assertResponse<T>(value: unknown): DesktopResponse<T> {
  if (!value || typeof value !== "object") {
    throw new Error("EchoFlow Processing Center returned an invalid response");
  }
  const candidate = value as Partial<DesktopResponse<T>>;
  if (
    candidate.protocol_version !== 1 ||
    typeof candidate.request_id !== "string" ||
    typeof candidate.ok !== "boolean"
  ) {
    throw new Error("EchoFlow Processing Center returned an incompatible response");
  }
  return candidate as DesktopResponse<T>;
}

function taskId(): string {
  return crypto.randomUUID();
}

function taskPayload(
  plan: ProcessingPreflight,
  options: PreflightOptions,
  execution: ExecutionOptions,
): Record<string, unknown> {
  return {
    job_id: plan.job_id,
    profile: options.profile,
    strategy_id: options.strategyId ?? null,
    audio_stream_index: options.audioStreamIndex ?? null,
    enhance: options.enhance ?? false,
    diarize: execution.diarize,
    allow_diarization_model_download: execution.allowDiarizationModelDownload,
    speakers: execution.speakers,
    min_speakers: execution.minSpeakers,
    max_speakers: execution.maxSpeakers,
    export_formats: execution.exportFormats,
  };
}

class TauriProcessingClient implements ProcessingClient {
  private async request<T>(method: string, params: Record<string, unknown>): Promise<T> {
    const { invoke } = await import("@tauri-apps/api/core");
    const request = {
      protocol_version: 1,
      request_id: crypto.randomUUID(),
      method,
      params,
    };
    const response = assertResponse<T>(
      await invoke<unknown>("desktop_request", { request }),
    );
    if (!response.ok || response.result === null) {
      throw new Error(response.error?.message ?? "EchoFlow could not complete that request");
    }
    return response.result;
  }

  private async startTask(task: Record<string, unknown>): Promise<ProcessingTaskStatus> {
    const { invoke } = await import("@tauri-apps/api/core");
    return invoke<ProcessingTaskStatus>("processing_start_task", { task });
  }

  readiness(profile: ProcessingProfile): Promise<ProcessingReadiness> {
    return this.request("processing.readiness", { profile });
  }

  jobs(): Promise<ProcessingJob[]> {
    return this.request("processing.jobs.list", {});
  }

  preflight(inputPath: string, options: PreflightOptions): Promise<ProcessingPreflight> {
    return this.request("processing.preflight", {
      input_path: inputPath,
      profile: options.profile,
      strategy_id: options.strategyId ?? null,
      audio_stream_index: options.audioStreamIndex ?? null,
      enhance: options.enhance ?? false,
    });
  }

  retryPreflight(sourceJobId: string, options: PreflightOptions): Promise<ProcessingPreflight> {
    return this.request("processing.retry.preflight", {
      source_job_id: sourceJobId,
      profile: options.profile,
      strategy_id: options.strategyId ?? null,
      audio_stream_index: options.audioStreamIndex ?? null,
      enhance: options.enhance ?? false,
    });
  }

  async discardJob(job: ProcessingJob): Promise<void> {
    await this.request("processing.job.discard", {
      job_id: job.job_id,
      expected_updated_at: job.updated_at,
    });
  }

  verifyModel(
    modelId: string,
  ): Promise<{ model_id: string; installed: boolean; resolved_revision: string | null }> {
    return this.request("processing.model.verify", { model_id: modelId });
  }

  startTranscription(
    inputPath: string,
    plan: ProcessingPreflight,
    options: PreflightOptions,
    execution: ExecutionOptions,
  ): Promise<ProcessingTaskStatus> {
    return this.startTask({
      task_id: taskId(),
      kind: "transcription_start",
      input_path: inputPath,
      ...taskPayload(plan, options, execution),
    });
  }

  retryTranscription(
    sourceJobId: string,
    plan: ProcessingPreflight,
    options: PreflightOptions,
    execution: ExecutionOptions,
  ): Promise<ProcessingTaskStatus> {
    return this.startTask({
      task_id: taskId(),
      kind: "transcription_retry",
      source_job_id: sourceJobId,
      ...taskPayload(plan, options, execution),
    });
  }

  resumeTranscription(
    job: ProcessingJob,
    execution: ExecutionOptions,
  ): Promise<ProcessingTaskStatus> {
    return this.startTask({
      task_id: taskId(),
      kind: "transcription_resume",
      job_id: job.job_id,
      diarize: execution.diarize,
      allow_diarization_model_download: execution.allowDiarizationModelDownload,
      speakers: execution.speakers,
      min_speakers: execution.minSpeakers,
      max_speakers: execution.maxSpeakers,
      export_formats: execution.exportFormats,
    });
  }

  installModel(modelId: string, revision?: string | null): Promise<ProcessingTaskStatus> {
    return this.startTask({
      task_id: taskId(),
      kind: "model_install",
      model_id: modelId,
      revision: revision ?? null,
    });
  }

  removeModel(model: ProcessingModel): Promise<ProcessingTaskStatus> {
    if (!model.resolved_revision) {
      return Promise.reject(new Error("Model is not installed"));
    }
    return this.startTask({
      task_id: taskId(),
      kind: "model_remove",
      model_id: model.model_id,
      expected_revision: model.resolved_revision,
    });
  }

  async taskStatus(taskIdValue: string): Promise<ProcessingTaskStatus> {
    const { invoke } = await import("@tauri-apps/api/core");
    return invoke<ProcessingTaskStatus>("processing_task_status", { taskId: taskIdValue });
  }

  async cancelTask(taskIdValue: string): Promise<ProcessingTaskStatus> {
    const { invoke } = await import("@tauri-apps/api/core");
    return invoke<ProcessingTaskStatus>("processing_cancel_task", { taskId: taskIdValue });
  }
}

class MockProcessingClient implements ProcessingClient {
  private taskCounter = 0;
  private modelMutation = 0;
  private tasks = new Map<string, ProcessingTaskStatus>();
  private models: ProcessingModel[] = [
    {
      model_id: "tiny",
      engine: "faster-whisper",
      estimated_cache_bytes: 157_286_400,
      quality_rank: 1,
      installed: false,
      resolved_revision: null,
      installed_size_bytes: null,
      verification: null,
    },
    {
      model_id: "small",
      engine: "faster-whisper",
      estimated_cache_bytes: 786_432_000,
      quality_rank: 2,
      installed: true,
      resolved_revision: "mock-small-revision",
      installed_size_bytes: 734_003_200,
      verification: "huggingface_snapshot_required_files_v1",
    },
    {
      model_id: "medium",
      engine: "faster-whisper",
      estimated_cache_bytes: 2_621_440_000,
      quality_rank: 3,
      installed: false,
      resolved_revision: null,
      installed_size_bytes: null,
      verification: null,
    },
  ];
  private jobMutation = 0;
  private jobRecords: ProcessingJob[] = [
    {
      job_id: "job-interrupted-7",
      recording_name: "oral-history-07.m4a",
      status: "interrupted",
      started_at: "2026-08-20T12:10:00+00:00",
      updated_at: "2026-08-20T12:35:00+00:00",
      total_segments: 12,
      completed_segments: 8,
      progress_fraction: 8 / 12,
      resumable: true,
      artifact_published: false,
      error_code: null,
      failure_message: null,
    },
    {
      job_id: "job-completed-2",
      recording_name: "interview-02.mp4",
      status: "completed",
      started_at: "2026-08-19T16:00:00+00:00",
      updated_at: "2026-08-19T16:48:00+00:00",
      total_segments: 9,
      completed_segments: 9,
      progress_fraction: 1,
      resumable: false,
      artifact_published: true,
      error_code: null,
      failure_message: null,
    },
  ];

  async readiness(profile: ProcessingProfile): Promise<ProcessingReadiness> {
    const recommendedModel = profile === "screening" ? "tiny" : profile === "accuracy" ? "medium" : "small";
    return {
      health: {
        status: "healthy",
        checks: [
          { check_id: "workspace", status: "pass", summary: "Private workspace is ready", required: true, error_code: null },
          { check_id: "ffmpeg", status: "pass", summary: "FFmpeg and FFprobe are available", required: true, error_code: null },
          { check_id: "system_resources", status: "pass", summary: "Local resources are available", required: true, error_code: null },
        ],
      },
      resources: {
        platform: "Linux",
        machine: "x86_64",
        effective_cpus: 8,
        effective_memory_available_bytes: 12_884_901_888,
        constraints: [],
      },
      policy: {
        profile,
        provisional: profile === "screening",
        cpu_threads: 8,
        memory_budget_bytes: 9_663_676_416,
        constraints: [],
      },
      strategies: [
        { strategy_id: "tiny-cpu-int8", model: "tiny", device: "cpu", compute_type: "int8", estimated_peak_memory_bytes: 1_342_177_280, estimated_peak_device_memory_bytes: 0, model_cache_bytes: 157_286_400, feasible: true, rejection_reasons: [], recommended: recommendedModel === "tiny" },
        { strategy_id: "small-cpu-int8", model: "small", device: "cpu", compute_type: "int8", estimated_peak_memory_bytes: 2_415_919_104, estimated_peak_device_memory_bytes: 0, model_cache_bytes: 786_432_000, feasible: true, rejection_reasons: [], recommended: recommendedModel === "small" },
        { strategy_id: "medium-cpu-int8", model: "medium", device: "cpu", compute_type: "int8", estimated_peak_memory_bytes: 4_563_402_752, estimated_peak_device_memory_bytes: 0, model_cache_bytes: 2_621_440_000, feasible: true, rejection_reasons: [], recommended: recommendedModel === "medium" },
      ],
      models: this.models.map((model) => ({ ...model })),
      recommended_model: recommendedModel,
      recommended_model_installed: this.models.some((model) => model.model_id === recommendedModel && model.installed),
    };
  }

  async jobs(): Promise<ProcessingJob[]> {
    return this.jobRecords.map((job) => ({ ...job }));
  }

  async preflight(inputPath: string, options: PreflightOptions): Promise<ProcessingPreflight> {
    const name = inputPath.split(/[\\/]/).filter(Boolean).at(-1) ?? inputPath;
    return this.plan(name, options);
  }

  async retryPreflight(_sourceJobId: string, options: PreflightOptions): Promise<ProcessingPreflight> {
    return this.plan("retry-recording.m4a", options);
  }

  async discardJob(job: ProcessingJob): Promise<void> {
    const current = this.jobRecords.find((item) => item.job_id === job.job_id);
    if (!current) throw new Error("Job does not exist");
    if (current.updated_at !== job.updated_at) throw new Error("Job state changed; refresh before discarding private state");
    if (current.status === "running") throw new Error("A running job cannot be discarded");
    this.jobRecords = this.jobRecords.filter((item) => item.job_id !== job.job_id);
  }

  async verifyModel(modelId: string) {
    const model = this.models.find((item) => item.model_id === modelId);
    if (!model) throw new Error("Unknown model");
    return { model_id: modelId, installed: model.installed, resolved_revision: model.resolved_revision };
  }

  async startTranscription(
    _inputPath: string,
    plan: ProcessingPreflight,
    _options: PreflightOptions,
    _execution: ExecutionOptions,
  ): Promise<ProcessingTaskStatus> {
    this.jobMutation += 1;
    this.jobRecords.unshift({
      job_id: plan.job_id,
      recording_name: plan.recording_name,
      status: "running",
      started_at: `2026-08-20T18:${String(this.jobMutation).padStart(2, "0")}:00+00:00`,
      updated_at: `2026-08-20T18:${String(this.jobMutation).padStart(2, "0")}:00+00:00`,
      total_segments: 10,
      completed_segments: 1,
      progress_fraction: 0.1,
      resumable: true,
      artifact_published: false,
      error_code: null,
      failure_message: null,
    });
    return this.newTask();
  }

  async retryTranscription(
    _sourceJobId: string,
    plan: ProcessingPreflight,
    options: PreflightOptions,
    execution: ExecutionOptions,
  ): Promise<ProcessingTaskStatus> {
    return this.startTranscription("mock-retry", plan, options, execution);
  }

  async resumeTranscription(job: ProcessingJob, _execution: ExecutionOptions): Promise<ProcessingTaskStatus> {
    const current = this.jobRecords.find((item) => item.job_id === job.job_id);
    if (!current || !current.resumable) throw new Error("Job is not resumable");
    current.status = "running";
    current.updated_at = "2026-08-20T18:30:00+00:00";
    return this.newTask();
  }

  async installModel(modelId: string): Promise<ProcessingTaskStatus> {
    const model = this.models.find((item) => item.model_id === modelId);
    if (!model) throw new Error("Unknown model");
    this.modelMutation += 1;
    model.installed = true;
    model.resolved_revision = `mock-${modelId}-revision-${this.modelMutation}`;
    model.installed_size_bytes = model.estimated_cache_bytes;
    model.verification = "huggingface_snapshot_required_files_v1";
    return this.newTask();
  }

  async removeModel(model: ProcessingModel): Promise<ProcessingTaskStatus> {
    const current = this.models.find((item) => item.model_id === model.model_id);
    if (!current || current.resolved_revision !== model.resolved_revision) {
      throw new Error("Model state changed; refresh before removing it");
    }
    current.installed = false;
    current.resolved_revision = null;
    current.installed_size_bytes = null;
    current.verification = null;
    return this.newTask();
  }

  async taskStatus(taskIdValue: string): Promise<ProcessingTaskStatus> {
    const task = this.tasks.get(taskIdValue);
    if (!task) throw new Error("Unknown processing task");
    if (task.state === "running") {
      task.state = "completed";
      task.exit_code = 0;
    }
    return { ...task };
  }

  async cancelTask(taskIdValue: string): Promise<ProcessingTaskStatus> {
    const task = this.tasks.get(taskIdValue);
    if (!task) throw new Error("Unknown processing task");
    task.state = "cancelled";
    task.exit_code = null;
    return { ...task };
  }

  private newTask(): ProcessingTaskStatus {
    this.taskCounter += 1;
    const status: ProcessingTaskStatus = {
      task_id: `mock-task-${this.taskCounter}`,
      state: "running",
      exit_code: null,
    };
    this.tasks.set(status.task_id, status);
    return { ...status };
  }

  private plan(recordingName: string, options: PreflightOptions): ProcessingPreflight {
    const model = options.profile === "screening" ? "tiny" : options.profile === "accuracy" ? "medium" : "small";
    const strategy = options.strategyId ?? `${model}-cpu-int8`;
    const multitrack = new URLSearchParams(window.location.search).get("multitrack") === "1";
    const audioStreams: ProcessingAudioStream[] = multitrack
      ? [
          {
            index: 1,
            codec: "aac",
            duration_seconds: 3_642.5,
            sample_rate_hz: 48_000,
            channels: 2,
            title: "Camera scratch",
            language: "eng",
            is_default: false,
          },
          {
            index: 3,
            codec: "pcm_s16le",
            duration_seconds: 3_642.5,
            sample_rate_hz: 48_000,
            channels: 1,
            title: "Lav microphone",
            language: "eng",
            is_default: true,
          },
        ]
      : [
          {
            index: 1,
            codec: "aac",
            duration_seconds: 3_642.5,
            sample_rate_hz: 48_000,
            channels: 2,
            title: null,
            language: null,
            is_default: false,
          },
        ];
    return {
      job_id: `job-planned-${this.jobMutation + 10}`,
      recording_name: recordingName,
      source_sha256: "e".repeat(64),
      container_format: "mov,mp4,m4a,3gp,3g2,mj2",
      duration_seconds: 3_642.5,
      audio_streams: audioStreams,
      selected_audio_stream_index: options.audioStreamIndex ?? audioStreams[0]!.index,
      audio_stream_selection_required: multitrack && options.audioStreamIndex == null,
      profile: options.profile,
      provisional: options.profile === "screening",
      strategy_id: strategy,
      engine: "faster-whisper",
      model,
      model_revision: `mock-${model}-revision`,
      device: "cpu",
      compute_type: "int8",
      cpu_threads: 8,
      decode_strategy: "ffmpeg_normalize",
      enhancement_enabled: options.enhance ?? false,
      estimated_disk_bytes: 612_368_384,
      estimated_peak_memory_bytes: model === "medium" ? 4_563_402_752 : model === "tiny" ? 1_342_177_280 : 2_415_919_104,
      memory_budget_bytes: 9_663_676_416,
      fits_memory_budget: true,
      warnings: ["paths_are_unreserved"],
    };
  }
}

export function createProcessingClient(): ProcessingClient {
  const params = new URLSearchParams(window.location.search);
  return params.get("e2e") === "1" ? new MockProcessingClient() : new TauriProcessingClient();
}
