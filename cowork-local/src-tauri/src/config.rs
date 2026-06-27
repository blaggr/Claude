use serde::Deserialize;
use serde_json::json;

use crate::error::AppError;

/// Subset of ~/.cowork-local/config.json that the updater script writes.
#[derive(Deserialize)]
struct OnDiskConfig {
    #[serde(rename = "preferredModel")]
    preferred_model: Option<String>,
}

fn config_path() -> Option<std::path::PathBuf> {
    let home = std::env::var_os("HOME")?;
    Some(std::path::Path::new(&home).join(".cowork-local").join("config.json"))
}

/// Persist the chosen default model (and the per-family resolutions) so the app
/// pre-selects it on the next launch. Shared by the in-app updater.
pub fn write_preferred_model(
    preferred: &str,
    resolved: &[(String, String)],
) -> Result<(), AppError> {
    let path = config_path().ok_or_else(|| AppError::Other("no HOME directory".into()))?;
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir).map_err(|e| AppError::Io(e.to_string()))?;
    }
    let resolved_map: serde_json::Map<String, serde_json::Value> = resolved
        .iter()
        .map(|(fam, slug)| (fam.clone(), json!(slug)))
        .collect();
    let body = json!({
        "preferredModel": preferred,
        "resolved": resolved_map,
    });
    std::fs::write(&path, serde_json::to_string_pretty(&body).unwrap_or_default())
        .map_err(|e| AppError::Io(e.to_string()))
}

/// Return the model the updater chose as the default, if any. The frontend
/// uses this to pre-select the newest Qwen/GLM model on launch.
#[tauri::command]
pub fn get_preferred_model() -> Option<String> {
    let home = std::env::var_os("HOME")?;
    let path = std::path::Path::new(&home)
        .join(".cowork-local")
        .join("config.json");
    let raw = std::fs::read_to_string(path).ok()?;
    let cfg: OnDiskConfig = serde_json::from_str(&raw).ok()?;
    cfg.preferred_model.filter(|s| !s.is_empty())
}
