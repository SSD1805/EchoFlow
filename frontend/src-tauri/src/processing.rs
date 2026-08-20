use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::io::Write;
use std::process::{Child, Command, ExitStatus, Stdio};
use std::sync::Mutex;
use tauri::State;

const MAX_TASK_BYTES: usize = 64 * 1024;

#[derive(Debug, Deserialize)]
#[serde(rename_all = "snake_case")]
enum TaskKind {
    TranscriptionStart,
    TranscriptionResume,
    TranscriptionRetry,
    ModelInstall,
    ModelRemove,
}

#[derive(Debug, Deserialize)]
struct TaskEnvelope {
    task_id: String,
    kind: TaskKind,
}

#[derive(Clone, Serialize)]
pub struct TaskStatus {
    task_id: String,
    state: &'static str,
    exit_code: Option<i32>,
}

struct ProcessEntry {
    child: Option<Child>,
    state: &'static str,
    exit_code: Option<i32>,
}

impl ProcessEntry {
    fn running(child: Child) -> Self {
        Self {
            child: Some(child),
            state: "running",
            exit_code: None,
        }
    }

    fn refresh(&mut self) -> Result<(), String> {
        let Some(child) = self.child.as_mut() else {
            return Ok(());
        };
        let status = child
            .try_wait()
            .map_err(|_| "EchoFlow could not inspect the local processing task".to_string())?;
        if let Some(status) = status {
            self.finish(status);
        }
        Ok(())
    }

    fn finish(&mut self, status: ExitStatus) {
        self.exit_code = status.code();
        self.state = if status.success() { "completed" } else { "failed" };
        self.child = None;
    }

    fn status(&self, task_id: &str) -> TaskStatus {
        TaskStatus {
            task_id: task_id.to_string(),
            state: self.state,
            exit_code: self.exit_code,
        }
    }
}

#[derive(Default)]
pub struct ProcessingProcesses {
    entries: Mutex<HashMap<String, ProcessEntry>>,
}

impl Drop for ProcessingProcesses {
    fn drop(&mut self) {
        let Ok(entries) = self.entries.get_mut() else {
            return;
        };
        for entry in entries.values_mut() {
            if let Some(child) = entry.child.as_mut() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

fn validate_envelope(task: &Value) -> Result<TaskEnvelope, String> {
    let envelope: TaskEnvelope = serde_json::from_value(task.clone())
        .map_err(|_| "Processing task was invalid or unsupported".to_string())?;
    if envelope.task_id.is_empty()
        || envelope.task_id.len() > 128
        || !envelope
            .task_id
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-' || byte == b'_')
    {
        return Err("Processing task identifier was invalid".to_string());
    }
    match envelope.kind {
        TaskKind::TranscriptionStart
        | TaskKind::TranscriptionResume
        | TaskKind::TranscriptionRetry
        | TaskKind::ModelInstall
        | TaskKind::ModelRemove => {}
    }
    Ok(envelope)
}

fn python_unavailable_message() -> String {
    if cfg!(debug_assertions) {
        "EchoFlow's local Python worker is unavailable. From the repository root run `uv sync --locked --extra transcription`, or set ECHOFLOW_PYTHON to a compatible interpreter."
            .to_string()
    } else {
        "EchoFlow's local Python worker is unavailable".to_string()
    }
}

#[tauri::command]
pub async fn processing_start_task(
    task: Value,
    processes: State<'_, ProcessingProcesses>,
) -> Result<TaskStatus, String> {
    let encoded = serde_json::to_vec(&task)
        .map_err(|_| "Could not encode local processing task".to_string())?;
    if encoded.len() > MAX_TASK_BYTES {
        return Err("Processing task exceeded the safe size limit".to_string());
    }
    let envelope = validate_envelope(&task)?;

    let mut entries = processes
        .entries
        .lock()
        .map_err(|_| "EchoFlow processing state is unavailable".to_string())?;
    if entries.contains_key(&envelope.task_id) {
        return Err("Processing task identifier is already in use".to_string());
    }

    let mut child = Command::new(crate::backend::configured_python())
        .args(["-m", "echoflow.desktop.processing_worker"])
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|_| python_unavailable_message())?;

    let write_result = child
        .stdin
        .take()
        .ok_or_else(|| "Could not open the EchoFlow processing worker".to_string())
        .and_then(|mut stdin| {
            stdin
                .write_all(&encoded)
                .map_err(|_| "Could not send the processing task to EchoFlow".to_string())
        });
    if let Err(message) = write_result {
        let _ = child.kill();
        let _ = child.wait();
        return Err(message);
    }

    let task_id = envelope.task_id;
    entries.insert(task_id.clone(), ProcessEntry::running(child));
    Ok(entries
        .get(&task_id)
        .expect("inserted processing task must exist")
        .status(&task_id))
}

#[tauri::command]
pub async fn processing_task_status(
    task_id: String,
    processes: State<'_, ProcessingProcesses>,
) -> Result<TaskStatus, String> {
    let mut entries = processes
        .entries
        .lock()
        .map_err(|_| "EchoFlow processing state is unavailable".to_string())?;
    let entry = entries
        .get_mut(&task_id)
        .ok_or_else(|| "Processing task is not known to this EchoFlow session".to_string())?;
    entry.refresh()?;
    Ok(entry.status(&task_id))
}

#[tauri::command]
pub async fn processing_cancel_task(
    task_id: String,
    processes: State<'_, ProcessingProcesses>,
) -> Result<TaskStatus, String> {
    let mut entries = processes
        .entries
        .lock()
        .map_err(|_| "EchoFlow processing state is unavailable".to_string())?;
    let entry = entries
        .get_mut(&task_id)
        .ok_or_else(|| "Processing task is not known to this EchoFlow session".to_string())?;
    entry.refresh()?;
    if let Some(child) = entry.child.as_mut() {
        child
            .kill()
            .map_err(|_| "EchoFlow could not stop the local processing task".to_string())?;
        let status = child
            .wait()
            .map_err(|_| "EchoFlow could not finish stopping the local processing task".to_string())?;
        entry.exit_code = status.code();
        entry.state = "cancelled";
        entry.child = None;
    }
    Ok(entry.status(&task_id))
}
