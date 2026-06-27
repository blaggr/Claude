use serde::Serialize;

/// Errors surfaced to the frontend. They serialize to a plain string so the
/// JS `invoke` rejection carries a readable message.
#[derive(Debug, thiserror::Error)]
pub enum AppError {
    #[error("no workspace folder has been selected")]
    NoWorkspace,
    #[error("path '{0}' is outside the workspace")]
    OutsideWorkspace(String),
    #[error("io error: {0}")]
    Io(String),
    #[error("ollama request failed: {0}")]
    Ollama(String),
    #[error("{0}")]
    Other(String),
}

impl Serialize for AppError {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        serializer.serialize_str(&self.to_string())
    }
}
