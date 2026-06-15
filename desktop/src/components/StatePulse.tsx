export type DaemonState = "idle" | "active";

/** Signature element: a dot that encodes the daemon's real state — cool when idle, a warm pulse
 * while it's thinking/working. */
export function StatePulse({ state }: { state: DaemonState }) {
  return (
    <span className={`pulse pulse--${state}`} role="status" aria-label={`daemon ${state}`}>
      <span className="pulse-dot" />
    </span>
  );
}
