import { useBusy } from "../state";
import { useTelemetry } from "../telemetry";
import { StatePulse } from "./StatePulse";

export function StatusBar({
  editing,
  onToggleEdit,
}: {
  editing: boolean;
  onToggleEdit: () => void;
}) {
  const { busy } = useBusy();
  const cost = useTelemetry<{ cost_usd: number }>("cost");
  return (
    <header className="statusbar">
      <div className="brand">
        <StatePulse state={busy ? "active" : "idle"} />
        <span className="wordmark">S.I.P.A.</span>
      </div>
      <div className="status-right">
        <span className="session">
          <span className="session-label">session</span>
          <span className="session-cost">${(cost?.cost_usd ?? 0).toFixed(4)}</span>
        </span>
        <button className={`edit-toggle ${editing ? "on" : ""}`} onClick={onToggleEdit}>
          {editing ? "done" : "edit"}
        </button>
      </div>
    </header>
  );
}
