import { useTelemetry } from "../telemetry";

type Agent = { id: number; task: string; status: "running" | "done" | "error" };
type AgentsSnapshot = { agents: Agent[] };

/** Background Agents tile — live status of detached `delegate_background` sub-agents, pushed on every
 * state change (telemetry topic "agents"). Newest first; the full result still lands in chat. */
export function AgentsModule() {
  const snap = useTelemetry<AgentsSnapshot>("agents");
  const agents = snap?.agents ?? [];
  if (agents.length === 0) return <p className="module-empty">no background agents</p>;
  return (
    <ul className="agents">
      {[...agents].reverse().map((a) => (
        <li key={a.id} className="agent">
          <span className={`agent-dot agent-dot--${a.status}`} />
          <span className="agent-task">{a.task}</span>
          <span className="agent-status">{a.status}</span>
        </li>
      ))}
    </ul>
  );
}
