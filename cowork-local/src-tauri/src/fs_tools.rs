use std::fs;

use tauri::State;

use crate::error::AppError;
use crate::state::AppState;

const MAX_READ_BYTES: u64 = 2 * 1024 * 1024; // 2 MiB guardrail for context size.

/// List directory entries (relative names, folders suffixed with '/').
#[tauri::command]
pub fn list_directory(state: State<AppState>, path: String) -> Result<Vec<String>, AppError> {
    let dir = state.resolve(&path)?;
    let mut out = Vec::new();
    for entry in fs::read_dir(&dir).map_err(|e| AppError::Io(e.to_string()))? {
        let entry = entry.map_err(|e| AppError::Io(e.to_string()))?;
        let name = entry.file_name().to_string_lossy().into_owned();
        let is_dir = entry.file_type().map(|t| t.is_dir()).unwrap_or(false);
        out.push(if is_dir { format!("{name}/") } else { name });
    }
    out.sort();
    Ok(out)
}

/// Read a UTF-8 text file inside the workspace.
#[tauri::command]
pub fn read_file(state: State<AppState>, path: String) -> Result<String, AppError> {
    let file = state.resolve(&path)?;
    let meta = fs::metadata(&file).map_err(|e| AppError::Io(e.to_string()))?;
    if meta.len() > MAX_READ_BYTES {
        return Err(AppError::Other(format!(
            "file is {} bytes; refusing to read more than {} bytes",
            meta.len(),
            MAX_READ_BYTES
        )));
    }
    fs::read_to_string(&file).map_err(|e| AppError::Io(e.to_string()))
}

/// Create or overwrite a UTF-8 text file, creating parent folders as needed.
/// Returns the number of bytes written.
#[tauri::command]
pub fn write_file(state: State<AppState>, path: String, content: String) -> Result<usize, AppError> {
    let file = state.resolve(&path)?;
    if let Some(parent) = file.parent() {
        fs::create_dir_all(parent).map_err(|e| AppError::Io(e.to_string()))?;
    }
    fs::write(&file, content.as_bytes()).map_err(|e| AppError::Io(e.to_string()))?;
    Ok(content.len())
}

/// Set the sandbox workspace directory. Must exist and be a directory.
#[tauri::command]
pub fn set_workspace(state: State<AppState>, path: String) -> Result<(), AppError> {
    let meta = fs::metadata(&path).map_err(|e| AppError::Io(e.to_string()))?;
    if !meta.is_dir() {
        return Err(AppError::Other("selected path is not a directory".into()));
    }
    state.set_workspace(path.into());
    Ok(())
}

#[tauri::command]
pub fn get_workspace(state: State<AppState>) -> Option<String> {
    state
        .workspace()
        .map(|p| p.to_string_lossy().into_owned())
}
