mod config;
mod error;
mod fs_tools;
mod models;
mod ollama;
mod shell;
mod state;

use state::AppState;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(AppState::default())
        .invoke_handler(tauri::generate_handler![
            ollama::ollama_chat,
            ollama::ollama_list_models,
            fs_tools::list_directory,
            fs_tools::read_file,
            fs_tools::write_file,
            fs_tools::set_workspace,
            fs_tools::get_workspace,
            shell::run_command,
            config::get_preferred_model,
            models::update_models,
        ])
        .run(tauri::generate_context!())
        .expect("error while running Cowork Local");
}
