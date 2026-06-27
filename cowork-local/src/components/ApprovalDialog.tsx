import { describeCall } from "../lib/tools";
import type { ToolEvent } from "../lib/types";

interface Props {
  evt: ToolEvent;
  onResolve: (approved: boolean) => void;
}

/**
 * Blocking modal shown before any side-effecting tool runs. The agent loop
 * awaits the user's decision here, so nothing touches disk or the shell
 * without an explicit click.
 */
export function ApprovalDialog({ evt, onResolve }: Props) {
  const detail =
    evt.name === "run_command"
      ? String(evt.args.command ?? "")
      : evt.name === "write_file"
        ? String(evt.args.path ?? "")
        : JSON.stringify(evt.args, null, 2);

  return (
    <div className="modal-backdrop">
      <div className="modal">
        <h3>Approval needed</h3>
        <p className="modal-summary">{describeCall(evt.name, evt.args)}</p>
        <pre className="modal-detail">{detail}</pre>
        {evt.name === "write_file" && typeof evt.args.content === "string" && (
          <pre className="modal-content-preview">
            {(evt.args.content as string).slice(0, 2000)}
            {(evt.args.content as string).length > 2000 ? "\n… (truncated)" : ""}
          </pre>
        )}
        <div className="modal-actions">
          <button className="btn-secondary" onClick={() => onResolve(false)}>
            Deny
          </button>
          <button className="btn-primary" onClick={() => onResolve(true)}>
            Approve &amp; run
          </button>
        </div>
      </div>
    </div>
  );
}
