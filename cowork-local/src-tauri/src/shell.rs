use std::time::Duration;

use serde::Serialize;
use tauri::State;
use tokio::process::Command;
use tokio::time::timeout;

use crate::error::AppError;
use crate::state::AppState;

const COMMAND_TIMEOUT: Duration = Duration::from_secs(120);

#[derive(Serialize)]
pub struct CommandResult {
    stdout: String,
    stderr: String,
    code: Option<i32>,
}

/// Run a shell command in the workspace directory. Approval is enforced in the
/// UI before this command is ever invoked; here we just execute, scope the
/// working directory to the workspace, and bound the runtime.
#[tauri::command]
pub async fn run_command(
    state: State<'_, AppState>,
    command: String,
) -> Result<CommandResult, AppError> {
    let cwd = state.workspace().ok_or(AppError::NoWorkspace)?;

    let mut cmd = build_command(&command);
    cmd.current_dir(&cwd)
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped());

    let child = cmd.spawn().map_err(|e| AppError::Io(e.to_string()))?;

    let output = match timeout(COMMAND_TIMEOUT, child.wait_with_output()).await {
        Ok(res) => res.map_err(|e| AppError::Io(e.to_string()))?,
        Err(_) => {
            return Err(AppError::Other(format!(
                "command timed out after {}s",
                COMMAND_TIMEOUT.as_secs()
            )))
        }
    };

    Ok(CommandResult {
        stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
        stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
        code: output.status.code(),
    })
}

#[cfg(unix)]
fn build_command(command: &str) -> Command {
    let mut cmd = Command::new("/bin/sh");
    cmd.arg("-c").arg(command);
    cmd
}

#[cfg(windows)]
fn build_command(command: &str) -> Command {
    let mut cmd = Command::new("cmd");
    cmd.arg("/C").arg(command);
    cmd
}
