import { type DaemonState, StatePulse } from "./StatePulse";

export function StatusBar({ state }: { state: DaemonState }) {
  return (
    <header className="statusbar">
      <div className="brand">
        <StatePulse state={state} />
        <span className="wordmark">S.I.P.A.</span>
      </div>
      <div className="session">
        <span className="session-label">session</span>
        <span className="session-cost">$0.0000</span>
      </div>
    </header>
  );
}
