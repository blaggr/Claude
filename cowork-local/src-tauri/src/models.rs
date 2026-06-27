use futures_util::StreamExt;
use serde::{Deserialize, Serialize};
use serde_json::json;
use tauri::ipc::Channel;

use crate::config;
use crate::error::AppError;

const OLLAMA_URL: &str = "http://127.0.0.1:11434";
const LIBRARY_SEARCH: &str = "https://ollama.com/search?q=";

/// Families tracked by the in-app updater, in default-preference order.
const FAMILIES: [&str; 2] = ["qwen", "glm"];

/// Progress events streamed to the UI while updating models.
#[derive(Serialize, Clone)]
#[serde(tag = "event", content = "data", rename_all = "camelCase")]
pub enum UpdateEvent {
    Status { message: String },
    Progress { model: String, status: String, percent: Option<u8> },
    Done { preferred: String, resolved: Vec<(String, String)> },
    Error { message: String },
}

/// Discover the newest Qwen/GLM base models published in the Ollama library,
/// pull them, record the default, and stream progress. Returns the preferred
/// model slug.
#[tauri::command]
pub async fn update_models(
    primary: Option<String>,
    on_event: Channel<UpdateEvent>,
) -> Result<String, AppError> {
    let client = reqwest::Client::new();
    let mut resolved: Vec<(String, String)> = Vec::new();

    for fam in FAMILIES {
        let _ = on_event.send(UpdateEvent::Status {
            message: format!("Checking the Ollama library for the latest {fam}…"),
        });
        match discover_latest(&client, fam).await {
            Ok(Some(slug)) => {
                let _ = on_event.send(UpdateEvent::Status {
                    message: format!("Latest {fam}: {slug} — pulling…"),
                });
                if let Err(e) = pull_model(&client, &slug, &on_event).await {
                    let _ = on_event.send(UpdateEvent::Status {
                        message: format!("Could not pull {slug}: {e}"),
                    });
                } else {
                    resolved.push((fam.to_string(), slug));
                }
            }
            Ok(None) => {
                let _ = on_event.send(UpdateEvent::Status {
                    message: format!("No {fam} base model is published in the Ollama library."),
                });
            }
            Err(e) => {
                let _ = on_event.send(UpdateEvent::Status {
                    message: format!("Lookup failed for {fam}: {e}"),
                });
            }
        }
    }

    if resolved.is_empty() {
        let msg = "No Qwen/GLM models could be resolved (offline, or none published).".to_string();
        let _ = on_event.send(UpdateEvent::Error { message: msg.clone() });
        return Err(AppError::Other(msg));
    }

    // Choose the default: requested primary family first, else first resolved.
    let primary = primary.unwrap_or_default().to_lowercase();
    let preferred = resolved
        .iter()
        .find(|(fam, _)| *fam == primary)
        .or_else(|| resolved.first())
        .map(|(_, slug)| slug.clone())
        .unwrap();

    config::write_preferred_model(&preferred, &resolved)?;

    let _ = on_event.send(UpdateEvent::Done {
        preferred: preferred.clone(),
        resolved,
    });
    Ok(preferred)
}

/// Parse the library search HTML for the highest-versioned base model of a
/// family. A "base" model is the family name followed only by version
/// digits/dots (e.g. `qwen3`, `glm4.6`) — this skips `qwen2.5-coder` etc.
async fn discover_latest(
    client: &reqwest::Client,
    family: &str,
) -> Result<Option<String>, AppError> {
    let url = format!("{LIBRARY_SEARCH}{family}");
    let html = client
        .get(&url)
        .header("User-Agent", "cowork-local-updater")
        .send()
        .await
        .map_err(|e| AppError::Other(e.to_string()))?
        .text()
        .await
        .map_err(|e| AppError::Other(e.to_string()))?;

    let mut best: Option<(Vec<u32>, String)> = None;
    for slug in extract_library_slugs(&html) {
        if let Some(version) = base_version(&slug, family) {
            let better = match &best {
                Some((bv, _)) => &version > bv,
                None => true,
            };
            if better {
                best = Some((version, slug));
            }
        }
    }
    Ok(best.map(|(_, slug)| slug))
}

/// Pull `name` via the local Ollama daemon, streaming download progress.
async fn pull_model(
    client: &reqwest::Client,
    name: &str,
    on_event: &Channel<UpdateEvent>,
) -> Result<(), AppError> {
    #[derive(Deserialize)]
    struct PullLine {
        #[serde(default)]
        status: String,
        #[serde(default)]
        total: Option<u64>,
        #[serde(default)]
        completed: Option<u64>,
        #[serde(default)]
        error: Option<String>,
    }

    let resp = client
        .post(format!("{OLLAMA_URL}/api/pull"))
        .json(&json!({ "name": name, "stream": true }))
        .send()
        .await
        .map_err(|e| AppError::Ollama(e.to_string()))?;

    if !resp.status().is_success() {
        let status = resp.status();
        let detail = resp.text().await.unwrap_or_default();
        return Err(AppError::Ollama(format!("{status}: {detail}")));
    }

    let mut stream = resp.bytes_stream();
    let mut buf = String::new();
    while let Some(chunk) = stream.next().await {
        let bytes = chunk.map_err(|e| AppError::Ollama(e.to_string()))?;
        buf.push_str(&String::from_utf8_lossy(&bytes));
        while let Some(nl) = buf.find('\n') {
            let line = buf[..nl].trim().to_string();
            buf.drain(..=nl);
            if line.is_empty() {
                continue;
            }
            if let Ok(p) = serde_json::from_str::<PullLine>(&line) {
                if let Some(err) = p.error {
                    return Err(AppError::Ollama(err));
                }
                let percent = match (p.completed, p.total) {
                    (Some(c), Some(t)) if t > 0 => Some(((c * 100) / t) as u8),
                    _ => None,
                };
                on_event
                    .send(UpdateEvent::Progress {
                        model: name.to_string(),
                        status: p.status,
                        percent,
                    })
                    .ok();
            }
        }
    }
    Ok(())
}

/// Extract every `<slug>` from `href="/library/<slug>"` occurrences.
fn extract_library_slugs(html: &str) -> Vec<String> {
    const MARKER: &str = "/library/";
    let mut out = Vec::new();
    let mut rest = html;
    while let Some(idx) = rest.find(MARKER) {
        let after = &rest[idx + MARKER.len()..];
        let slug: String = after
            .chars()
            .take_while(|c| c.is_ascii_alphanumeric() || *c == '.' || *c == '-' || *c == '_')
            .collect();
        let advance = slug.len().max(1).min(after.len());
        if !slug.is_empty() {
            out.push(slug);
        }
        rest = &after[advance..];
    }
    out
}

/// If `slug` is `family` + only version chars, return the parsed version.
/// `qwen3` -> [3]; `qwen2.5` -> [2,5]; `qwen` -> [0]; `qwen2.5-coder` -> None.
fn base_version(slug: &str, family: &str) -> Option<Vec<u32>> {
    let rest = slug.strip_prefix(family)?;
    if !rest.chars().all(|c| c.is_ascii_digit() || c == '.') {
        return None;
    }
    if rest.is_empty() {
        return Some(vec![0]);
    }
    let parts: Vec<u32> = rest
        .split('.')
        .filter(|s| !s.is_empty())
        .filter_map(|s| s.parse().ok())
        .collect();
    if parts.is_empty() {
        Some(vec![0])
    } else {
        Some(parts)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ranks_base_models() {
        assert_eq!(base_version("qwen3", "qwen"), Some(vec![3]));
        assert_eq!(base_version("qwen2.5", "qwen"), Some(vec![2, 5]));
        assert_eq!(base_version("qwen", "qwen"), Some(vec![0]));
        assert_eq!(base_version("qwen2.5-coder", "qwen"), None);
        assert_eq!(base_version("glm4.6", "glm"), Some(vec![4, 6]));
        assert!(vec![3u32] > vec![2u32, 5]);
    }

    #[test]
    fn extracts_slugs() {
        let html = r#"<a href="/library/qwen3">..</a><a href="/library/qwen2.5-coder">"#;
        let slugs = extract_library_slugs(html);
        assert!(slugs.contains(&"qwen3".to_string()));
        assert!(slugs.contains(&"qwen2.5-coder".to_string()));
    }
}
