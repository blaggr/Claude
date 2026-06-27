use futures_util::StreamExt;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tauri::ipc::Channel;

use crate::error::AppError;

const OLLAMA_URL: &str = "http://127.0.0.1:11434";

/// Streaming events sent to the frontend over a Tauri Channel. Serializes as
/// `{ "event": "...", "data": { ... } }` to match the TS discriminated union.
#[derive(Serialize, Clone)]
#[serde(tag = "event", content = "data", rename_all = "camelCase")]
pub enum StreamEvent {
    Token { content: String },
    ToolCalls { calls: Vec<ToolCallOut> },
    Done { reason: String },
    Error { message: String },
}

#[derive(Serialize, Clone)]
pub struct ToolCallOut {
    id: String,
    function: FunctionOut,
}

#[derive(Serialize, Clone)]
pub struct FunctionOut {
    name: String,
    arguments: Value,
}

// ---- Ollama wire format (subset we care about) ----

#[derive(Deserialize)]
struct OllamaLine {
    #[serde(default)]
    message: Option<OllamaMessage>,
    #[serde(default)]
    done: bool,
    #[serde(default)]
    done_reason: Option<String>,
}

#[derive(Deserialize)]
struct OllamaMessage {
    #[serde(default)]
    content: String,
    #[serde(default)]
    tool_calls: Option<Vec<OllamaToolCall>>,
}

#[derive(Deserialize)]
struct OllamaToolCall {
    function: OllamaFunction,
}

#[derive(Deserialize)]
struct OllamaFunction {
    name: String,
    #[serde(default)]
    arguments: Value,
}

/// Stream a chat completion from the local Ollama server, forwarding tokens
/// and tool calls to the frontend as they arrive. Messages and tools are
/// passed through as raw JSON so the Ollama schema stays the source of truth.
#[tauri::command]
pub async fn ollama_chat(
    model: String,
    messages: Vec<Value>,
    tools: Vec<Value>,
    on_event: Channel<StreamEvent>,
) -> Result<(), AppError> {
    let body = json!({
        "model": model,
        "messages": messages,
        "tools": tools,
        "stream": true,
    });

    let client = reqwest::Client::new();
    let resp = client
        .post(format!("{OLLAMA_URL}/api/chat"))
        .json(&body)
        .send()
        .await
        .map_err(|e| AppError::Ollama(e.to_string()))?;

    if !resp.status().is_success() {
        let status = resp.status();
        let detail = resp.text().await.unwrap_or_default();
        let _ = on_event.send(StreamEvent::Error {
            message: format!("Ollama returned {status}: {detail}"),
        });
        return Err(AppError::Ollama(format!("{status}: {detail}")));
    }

    let mut stream = resp.bytes_stream();
    let mut buf = String::new();
    let mut tool_seq = 0u32;
    let mut reason = "stop".to_string();

    while let Some(chunk) = stream.next().await {
        let bytes = chunk.map_err(|e| AppError::Ollama(e.to_string()))?;
        buf.push_str(&String::from_utf8_lossy(&bytes));

        // Ollama emits newline-delimited JSON objects.
        while let Some(nl) = buf.find('\n') {
            let line = buf[..nl].trim().to_string();
            buf.drain(..=nl);
            if line.is_empty() {
                continue;
            }
            if let Some(r) = handle_line(&line, &on_event, &mut tool_seq) {
                reason = r;
            }
        }
    }

    // Flush any trailing object without a newline terminator.
    let tail = buf.trim();
    if !tail.is_empty() {
        if let Some(r) = handle_line(tail, &on_event, &mut tool_seq) {
            reason = r;
        }
    }

    let _ = on_event.send(StreamEvent::Done { reason });
    Ok(())
}

/// Parse one NDJSON line, emitting token/tool events. Returns a done reason if
/// this line marks completion.
fn handle_line(
    line: &str,
    on_event: &Channel<StreamEvent>,
    tool_seq: &mut u32,
) -> Option<String> {
    let parsed: OllamaLine = match serde_json::from_str(line) {
        Ok(p) => p,
        Err(_) => return None, // skip anything we can't parse
    };

    if let Some(msg) = parsed.message {
        if !msg.content.is_empty() {
            let _ = on_event.send(StreamEvent::Token {
                content: msg.content,
            });
        }
        if let Some(calls) = msg.tool_calls {
            let out: Vec<ToolCallOut> = calls
                .into_iter()
                .map(|c| {
                    *tool_seq += 1;
                    ToolCallOut {
                        id: format!("call_{tool_seq}"),
                        function: FunctionOut {
                            name: c.function.name,
                            arguments: c.function.arguments,
                        },
                    }
                })
                .collect();
            if !out.is_empty() {
                let _ = on_event.send(StreamEvent::ToolCalls { calls: out });
            }
        }
    }

    if parsed.done {
        Some(parsed.done_reason.unwrap_or_else(|| "stop".to_string()))
    } else {
        None
    }
}

/// Return the names of models installed in the local Ollama instance.
#[tauri::command]
pub async fn ollama_list_models() -> Result<Vec<String>, AppError> {
    #[derive(Deserialize)]
    struct Tags {
        models: Vec<Model>,
    }
    #[derive(Deserialize)]
    struct Model {
        name: String,
    }

    let client = reqwest::Client::new();
    let tags: Tags = client
        .get(format!("{OLLAMA_URL}/api/tags"))
        .send()
        .await
        .map_err(|e| AppError::Ollama(e.to_string()))?
        .json()
        .await
        .map_err(|e| AppError::Ollama(e.to_string()))?;

    Ok(tags.models.into_iter().map(|m| m.name).collect())
}
