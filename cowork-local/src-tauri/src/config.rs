use serde::Deserialize;

/// Subset of ~/.cowork-local/config.json that the updater script writes.
#[derive(Deserialize)]
struct OnDiskConfig {
    #[serde(rename = "preferredModel")]
    preferred_model: Option<String>,
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
