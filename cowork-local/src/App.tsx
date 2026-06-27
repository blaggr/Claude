import { useEffect, useRef, useState } from "react";
import { ApprovalDialog } from "./components/ApprovalDialog";
import { MessageBubble } from "./components/MessageBubble";
import { ToolCard } from "./components/ToolCard";
import { UpdateDialog } from "./components/UpdateDialog";
import { runAgent, SYSTEM_PROMPT } from "./lib/agent";
import { listModels } from "./lib/ollama";
import { pickDefaultModel } from "./lib/models";
import { updateModels } from "./lib/update";
import type { ChatMessage, ToolEvent } from "./lib/types";
import { getWorkspace, pickWorkspace } from "./lib/workspace";

type FeedItem =
  | { kind: "msg"; id: string; role: "user" | "assistant"; text: string }
  | { kind: "tool"; id: string; evt: ToolEvent };

let idCounter = 0;
const nextId = () => `f${idCounter++}`;

export function App() {
  const [models, setModels] = useState<string[]>([]);
  const [model, setModel] = useState<string>("");
  const [workspace, setWorkspace] = useState<string | null>(null);
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<ToolEvent | null>(null);
  const [updating, setUpdating] = useState(false);
  const [updateOpen, setUpdateOpen] = useState(false);
  const [updateLines, setUpdateLines] = useState<string[]>([]);
  const [updateError, setUpdateError] = useState<string | null>(null);

  // Canonical transcript passed to the model (excludes UI-only metadata).
  const convo = useRef<ChatMessage[]>([{ role: "system", content: SYSTEM_PROMPT }]);
  const stopFlag = useRef(false);
  const approvalResolver = useRef<((ok: boolean) => void) | null>(null);
  const activeAssistantId = useRef<string | null>(null);
  const feedEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listModels()
      .then(async (m) => {
        setModels(m);
        if (m.length) {
          const preferred = await pickDefaultModel(m);
          setModel((cur) => cur || preferred);
        }
      })
      .catch((e) => setError(`Could not reach Ollama: ${e}. Is it running?`));
    getWorkspace().then(setWorkspace).catch(() => {});
  }, []);

  useEffect(() => {
    feedEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [feed]);

  function patchTool(id: string, patch: Partial<ToolEvent>) {
    setFeed((f) =>
      f.map((it) =>
        it.kind === "tool" && it.evt.id === id
          ? { ...it, evt: { ...it.evt, ...patch } }
          : it
      )
    );
  }

  async function onUpdateModels() {
    setUpdateOpen(true);
    setUpdating(true);
    setUpdateError(null);
    setUpdateLines([]);
    try {
      const preferred = await updateModels(null, {
        onLine: (t) => setUpdateLines((l) => [...l, t]),
      });
      const refreshed = await listModels();
      setModels(refreshed);
      if (refreshed.includes(preferred)) {
        setModel(preferred);
      } else {
        const match = refreshed.find((m) => m.split(":")[0] === preferred.split(":")[0]);
        if (match) setModel(match);
      }
    } catch (e) {
      setUpdateError(e instanceof Error ? e.message : String(e));
    } finally {
      setUpdating(false);
    }
  }

  async function onChooseWorkspace() {
    try {
      const ws = await pickWorkspace();
      if (ws) setWorkspace(ws);
    } catch (e) {
      setError(String(e));
    }
  }

  async function send() {
    const text = input.trim();
    if (!text || running) return;
    if (!workspace) {
      setError("Choose a workspace folder first.");
      return;
    }
    if (!model) {
      setError("No model selected. Install one with `ollama pull <model>`.");
      return;
    }

    setError(null);
    setInput("");
    stopFlag.current = false;
    setRunning(true);

    const userId = nextId();
    setFeed((f) => [...f, { kind: "msg", id: userId, role: "user", text }]);
    convo.current.push({ role: "user", content: text });

    try {
      const updated = await runAgent(model, convo.current, {
        onAssistantStart: () => {
          const id = nextId();
          activeAssistantId.current = id;
          setFeed((f) => [...f, { kind: "msg", id, role: "assistant", text: "" }]);
        },
        onToken: (t) => {
          const id = activeAssistantId.current;
          setFeed((f) =>
            f.map((it) =>
              it.kind === "msg" && it.id === id ? { ...it, text: it.text + t } : it
            )
          );
        },
        onToolEvent: (evt) => {
          setFeed((f) => [...f, { kind: "tool", id: evt.id, evt }]);
        },
        onToolEventUpdate: patchTool,
        requestApproval: (evt) =>
          new Promise<boolean>((resolve) => {
            approvalResolver.current = resolve;
            setPending(evt);
          }),
        shouldStop: () => stopFlag.current,
      });
      convo.current = updated;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
      activeAssistantId.current = null;
    }
  }

  function resolveApproval(ok: boolean) {
    setPending(null);
    approvalResolver.current?.(ok);
    approvalResolver.current = null;
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          Cowork <span className="brand-local">local</span>
        </div>
        <div className="controls">
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            disabled={running || !models.length}
          >
            {models.length ? (
              models.map((m) => <option key={m}>{m}</option>)
            ) : (
              <option>no models</option>
            )}
          </select>
          <button className="btn-secondary" onClick={onChooseWorkspace} disabled={running}>
            {workspace ? shorten(workspace) : "Choose workspace…"}
          </button>
          <button
            className="btn-secondary"
            onClick={() => void onUpdateModels()}
            disabled={running || updating}
            title="Find and pull the newest Qwen / GLM models"
          >
            {updating ? "Updating…" : "Update models"}
          </button>
        </div>
      </header>

      <main className="feed">
        {feed.length === 0 && (
          <div className="empty">
            <p>Your private coworker is ready.</p>
            <p className="muted">
              Everything runs locally — the only network call is to Ollama on
              this machine. Pick a workspace folder and ask it to do something.
            </p>
          </div>
        )}
        {feed.map((it) =>
          it.kind === "msg" ? (
            <MessageBubble
              key={it.id}
              role={it.role}
              text={it.text}
              streaming={running && it.id === activeAssistantId.current}
            />
          ) : (
            <ToolCard key={it.id} evt={it.evt} />
          )
        )}
        <div ref={feedEnd} />
      </main>

      {error && <div className="error-bar">{error}</div>}

      <footer className="composer">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={
            workspace ? "Ask your coworker to do something…" : "Choose a workspace to begin…"
          }
          rows={2}
        />
        {running ? (
          <button className="btn-stop" onClick={() => (stopFlag.current = true)}>
            Stop
          </button>
        ) : (
          <button className="btn-primary" onClick={() => void send()}>
            Send
          </button>
        )}
      </footer>

      {pending && <ApprovalDialog evt={pending} onResolve={resolveApproval} />}
      {updateOpen && (
        <UpdateDialog
          lines={updateLines}
          running={updating}
          error={updateError}
          onClose={() => setUpdateOpen(false)}
        />
      )}
    </div>
  );
}

function shorten(p: string): string {
  const parts = p.split("/");
  return parts.length > 2 ? "…/" + parts.slice(-2).join("/") : p;
}
