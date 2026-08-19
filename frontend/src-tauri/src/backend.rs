use serde_json::Value;
use std::env;
use std::io::Write;
use std::process::{Command, Stdio};

const MAX_REQUEST_BYTES: usize = 128 * 1024;

fn run_backend_request(request: Value) -> Result<Value, String> {
    let encoded = serde_json::to_vec(&request).map_err(|_| "Could not encode desktop request".to_string())?;
    if encoded.len() > MAX_REQUEST_BYTES {
        return Err("Desktop request exceeded the safe size limit".to_string());
    }

    let python = env::var("ECHOFLOW_PYTHON").unwrap_or_else(|_| "python".to_string());
    let mut child = Command::new(python)
        .args(["-m", "echoflow.desktop.bridge"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|_| "EchoFlow's local Python service is unavailable".to_string())?;

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
        return Err("EchoFlow's local Python service exited unexpectedly".to_string());
    }

    serde_json::from_slice(&output.stdout)
        .map_err(|_| "EchoFlow's local Python service returned an invalid response".to_string())
}

#[tauri::command]
pub async fn desktop_request(request: Value) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || run_backend_request(request))
        .await
        .map_err(|_| "EchoFlow's local service task could not be completed".to_string())?
}
