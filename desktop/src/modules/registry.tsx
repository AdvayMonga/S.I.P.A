import type { ComponentType } from "react";

import { Chat } from "../components/Chat";
import { CostModule } from "./Cost";
import { ThreadsModule } from "./Threads";

/** A dashboard module = one capability's tile. `w`/`h` are its footprint in grid units (cols=12).
 * Each capability gets its own component, built individually; placeholders until their data exists. */
export type Module = { id: string; title: string; w: number; h: number; Component: ComponentType };

function Placeholder({ note }: { note: string }) {
  return <p className="module-empty">{note}</p>;
}

const SchedulerModule = () => <Placeholder note="scheduled tasks — not wired yet" />;

// `id: "agents"` is kept (not "threads") so existing saved layouts keep this tile in place — it's
// the same panel slot, now the switchboard. Title/component changed to Threads.
export const MODULES: Module[] = [
  { id: "chat", title: "Chat", w: 7, h: 12, Component: Chat },
  { id: "cost", title: "Token Usage", w: 5, h: 4, Component: CostModule },
  { id: "agents", title: "Threads", w: 5, h: 4, Component: ThreadsModule },
  { id: "scheduler", title: "Scheduler", w: 5, h: 4, Component: SchedulerModule },
];

// Default arrangement (chat large on the left; capability tiles stacked on the right).
export const DEFAULT_LAYOUT = [
  { i: "chat", x: 0, y: 0, w: 7, h: 12 },
  { i: "cost", x: 7, y: 0, w: 5, h: 4 },
  { i: "agents", x: 7, y: 4, w: 5, h: 4 },
  { i: "scheduler", x: 7, y: 8, w: 5, h: 4 },
];
