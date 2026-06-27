interface Props {
  lines: string[];
  running: boolean;
  error: string | null;
  onClose: () => void;
}

/** Live progress panel for the in-app model updater. */
export function UpdateDialog({ lines, running, error, onClose }: Props) {
  return (
    <div className="modal-backdrop">
      <div className="modal">
        <h3>{running ? "Updating models…" : error ? "Update failed" : "Models updated"}</h3>
        <pre className="modal-detail update-log">
          {lines.length ? lines.join("\n") : "Starting…"}
          {error ? `\n\n${error}` : ""}
        </pre>
        <div className="modal-actions">
          <button className="btn-primary" onClick={onClose} disabled={running}>
            {running ? "Working…" : "Close"}
          </button>
        </div>
      </div>
    </div>
  );
}
