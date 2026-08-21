#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod backend;
mod processing;

fn main() {
    tauri::Builder::default()
        .manage(processing::ProcessingProcesses::default())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            backend::desktop_request,
            backend::transcript_tools_request,
            processing::processing_start_task,
            processing::processing_task_status,
            processing::processing_cancel_task,
        ])
        .run(tauri::generate_context!())
        .expect("EchoFlow desktop host could not start");
}
