import type { ComponentType } from "react";

import { Chat } from "../components/Chat";
import { CostModule } from "./Cost";
import { SchedulerModule } from "./Scheduler";
import { ThreadsModule } from "./Threads";

/** A dashboard module = one capability's tile. `w`/`h` are its footprint in grid units (cols=12).
 * Each capability gets its own component, built individually; placeholders until their data exists. */
export type Module = { id: string; title: string; w: number; h: number; Component: ComponentType };

// `id: "agents"` is kept (not "threads") so existing saved layouts keep this tile in place — it's
// the same panel slot, now the switchboard. Title/component changed to Threads.
export const MODULES: Module[] = [
  { id: "chat", title: "Chat", w: 7, h: 12, Component: Chat },
  { id: "cost", title: "Token Usage", w: 5, h: 3, Component: CostModule },
  { id: "agents", title: "Threads", w: 5, h: 6, Component: ThreadsModule },
  { id: "scheduler", title: "Scheduler", w: 5, h: 3, Component: SchedulerModule },
];

// Default arrangement: chat large on the left; right column = a 12-row stack that bottoms out level
// with chat. Threads gets the lion's share (h6, the switchboard); Cost/Scheduler flank it at h3.
export const DEFAULT_LAYOUT = [
  { i: "chat", x: 0, y: 0, w: 7, h: 12 },
  { i: "cost", x: 7, y: 0, w: 5, h: 3 },
  { i: "agents", x: 7, y: 3, w: 5, h: 6 },
  { i: "scheduler", x: 7, y: 9, w: 5, h: 3 },
];
