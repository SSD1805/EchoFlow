#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod backend;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![backend::desktop_request])
        .run(tauri::generate_context!())
        .expect("EchoFlow desktop host could not start");
}
