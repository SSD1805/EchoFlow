use serde_json::Value;
use std::env;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

const MAX_REQUEST_BYTES: usize = 128 * 1024;

pub(crate) fn configured_python() -> PathBuf {
    if let Ok(value) = env::var("ECHOFLOW_PYTHON") {
        if !value.trim().is_empty() {
            return PathBuf::from(value);
        }
    }

    if cfg!(debug_assertions) {
        let repo_root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let candidate = if cfg!(windows) {
            repo_root.join(".venv").join("Scripts").join("python.exe")
        } else {
            repo_root.join(".venv").join("bin").join("python")
        };
        if candidate.is_file() {
            return candidate;
        }
    }

    PathBuf::from("python")
}

fn python_unavailable_message() -> String {
    if cfg!(debug_assertions) {
        "EchoFlow's local Python service is unavailable. From the repository root run `uv sync --locked --extra transcription`, or set ECHOFLOW_PYTHON to a compatible interpreter."
            .to_string()
    } else {
        "EchoFlow's local Python service is unavailable".to_string()
    }
}

fn python_exit_message() -> String {
    if cfg!(debug_assertions) {
        "EchoFlow's local Python service exited unexpectedly. From frontend run `npm run doctor:desktop` to verify the source environment before retrying."
            .to_string()
    } else {
        "EchoFlow's local Python service exited unexpectedly".to_string()
    }
}

fn run_python_request(module: &'static str, request: Value) -> Result<Value, String> {
    let encoded = serde_json::to_vec(&request)
        .map_err(|_| "Could not encode desktop request".to_string())?;
    if encoded.len() > MAX_REQUEST_BYTES {
        return Err("Desktop request exceeded the safe size limit".to_string());
    }

    let mut child = Command::new(configured_python())
        .args(["-m", module])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|_| python_unavailable_message())?;

    let mut stdin = child
        .stdin
        .take()
        .ok_or_else(|| "Could not open the EchoFlow desktop bridge".to_string())?;
    stdin
        .write_all(&encoded)
        .map_err(|_| "Could not send the request to EchoFlow".to_string())?;
    drop(stdin);

    let output = child
        .wait_with_output()
        .map_err(|_| "EchoFlow's local Python service did not finish cleanly".to_string())?;
    if !output.status.success() {
        return Err(python_exit_message());
    }

    serde_json::from_slice(&output.stdout)
        .map_err(|_| "EchoFlow's local Python service returned an invalid response".to_string())
}

async fn request_module(module: &'static str, request: Value) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || run_python_request(module, request))
        .await
        .map_err(|_| "EchoFlow's local service task could not be completed".to_string())?
}

pub(crate) async fn playback_authorization_request(request: Value) -> Result<Value, String> {
    request_module("echoflow.desktop.playback_bridge", request).await
}

#[tauri::command]
pub async fn desktop_request(request: Value) -> Result<Value, String> {
    request_module("echoflow.desktop.bridge", request).await
}

#[tauri::command]
pub async fn transcript_tools_request(request: Value) -> Result<Value, String> {
    request_module("echoflow.desktop.transcript_tools_bridge", request).await
}

#[tauri::command]
pub async fn lifecycle_request(request: Value) -> Result<Value, String> {
    request_module("echoflow.desktop.custody_bridge", request).await
}
