#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod backend;
mod playback;
mod processing;

fn main() {
    let playback_sessions = playback::PlaybackSessions::default();
    let playback_protocol = playback_sessions.clone();

    tauri::Builder::default()
        .manage(processing::ProcessingProcesses::default())
        .manage(playback_sessions)
        .plugin(tauri_plugin_dialog::init())
        .register_asynchronous_uri_scheme_protocol(
            "scholion-media",
            move |_context, request, responder| {
                responder.respond(playback_protocol.protocol_response(request));
            },
        )
        .invoke_handler(tauri::generate_handler![
            backend::desktop_request,
            backend::transcript_tools_request,
            backend::lifecycle_request,
            processing::processing_start_task,
            processing::processing_task_status,
            processing::processing_cancel_task,
            playback::playback_prepare,
            playback::playback_release,
        ])
        .run(tauri::generate_context!())
        .expect("Scholion desktop host could not start");
}
