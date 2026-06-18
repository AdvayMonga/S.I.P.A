import { invoke } from "@tauri-apps/api/core";
import { useEffect, useState } from "react";

import { useTelemetry } from "../telemetry";

type Task = {
  id: string;
  prompt: string;
  cadence: string;
  enabled: boolean;
  last_run: string | null;
  due: boolean;
};

// "3d ago" / "2h ago" / "just now" from an ISO timestamp; "never run" if it hasn't fired.
function ago(iso: string | null): string {
  if (!iso) return "never run";
  const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return "just now";
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

/** Scheduler tile — the recurring tasks the bot runs proactively (scheduler MCP server). Read-only:
 * seeds from `:snapshot` on mount, re-fetches after each turn (cost telemetry) so a newly scheduled /
 * cancelled / fired task stays current. Editing is via chat for now (see BACKLOG: interactive tile). */
export function SchedulerModule() {
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const cost = useTelemetry("cost"); // a completed turn may have changed the schedule → re-fetch

  useEffect(() => {
    let cancelled = false;
    (async () => {
      // Retry until the daemon is reachable (it may still be starting), like the thread list.
      for (;;) {
        try {
          const snap = JSON.parse(await invoke<string>("snapshot")) as { scheduled: Task[] };
          if (!cancelled) setTasks(snap.scheduled);
          return;
        } catch {
          if (cancelled) return;
          await new Promise((r) => setTimeout(r, 1000));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [cost]);

  if (!tasks) return <p className="module-empty">connecting…</p>;
  if (tasks.length === 0) return <p className="module-empty">no scheduled tasks</p>;

  return (
    <ul className="sched-list">
      {tasks.map((t) => (
        <li key={t.id} className={`sched${t.enabled ? "" : " sched--off"}`}>
          <span className={`sched-dot${t.due && t.enabled ? " sched-dot--due" : ""}`} />
          <span className="sched-label" title={t.prompt}>
            {t.prompt}
          </span>
          <span className="sched-meta">
            <span className="sched-cadence">{t.cadence}</span>
            <span className="sched-run">{t.enabled ? ago(t.last_run) : "off"}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}
