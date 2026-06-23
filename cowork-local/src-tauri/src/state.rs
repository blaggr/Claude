use std::path::{Path, PathBuf};
use std::sync::Mutex;

use crate::error::AppError;

/// Process-wide application state. The workspace is the single directory the
/// agent is allowed to touch; every file path is resolved and validated
/// against it so the model cannot reach outside the sandbox.
#[derive(Default)]
pub struct AppState {
    workspace: Mutex<Option<PathBuf>>,
}

impl AppState {
    pub fn set_workspace(&self, path: PathBuf) {
        *self.workspace.lock().unwrap() = Some(path);
    }

    pub fn workspace(&self) -> Option<PathBuf> {
        self.workspace.lock().unwrap().clone()
    }

    /// Resolve a user/model-supplied relative path to an absolute path that is
    /// guaranteed to live inside the workspace. Rejects absolute paths and any
    /// traversal that escapes the root.
    pub fn resolve(&self, rel: &str) -> Result<PathBuf, AppError> {
        let root = self
            .workspace()
            .ok_or_else(|| AppError::NoWorkspace)?;
        let root = canonicalize_existing(&root)?;

        let candidate = root.join(rel);
        // Normalize without requiring the target to exist (it may be a new file).
        let normalized = normalize(&candidate);

        if !normalized.starts_with(&root) {
            return Err(AppError::OutsideWorkspace(rel.to_string()));
        }
        Ok(normalized)
    }
}

/// Canonicalize a path that is expected to exist (the workspace root).
fn canonicalize_existing(p: &Path) -> Result<PathBuf, AppError> {
    std::fs::canonicalize(p).map_err(|e| AppError::Io(e.to_string()))
}

/// Lexically normalize a path, collapsing `.` and `..` without hitting disk.
/// This is what lets us validate paths to not-yet-created files.
fn normalize(p: &Path) -> PathBuf {
    use std::path::Component;
    let mut out = PathBuf::new();
    for comp in p.components() {
        match comp {
            Component::ParentDir => {
                out.pop();
            }
            Component::CurDir => {}
            other => out.push(other.as_os_str()),
        }
    }
    out
}
