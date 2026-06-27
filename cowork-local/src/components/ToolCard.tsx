import type { ToolEvent } from "../lib/types";

const STATUS_LABEL: Record<ToolEvent["status"], string> = {
  pending: "pending",
  approved: "approved",
  denied: "denied",
  ok: "done",
  error: "error",
};

function summarize(evt: ToolEvent): string {
  const a = evt.args;
  switch (evt.name) {
    case "run_command":
      return String(a.command ?? "");
    case "read_file":
    case "list_directory":
      return String(a.path ?? "");
    case "write_file":
      return String(a.path ?? "");
    default:
      return JSON.stringify(a);
  }
}

export function ToolCard({ evt }: { evt: ToolEvent }) {
  return (
    <div className={`tool-card status-${evt.status}`}>
      <div className="tool-card-head">
        <span className="tool-name">{evt.name}</span>
        <span className={`tool-status status-${evt.status}`}>
          {STATUS_LABEL[evt.status]}
        </span>
      </div>
      <code className="tool-arg">{summarize(evt)}</code>
      {evt.result && evt.status !== "pending" && (
        <pre className="tool-result">{evt.result}</pre>
      )}
    </div>
  );
}
