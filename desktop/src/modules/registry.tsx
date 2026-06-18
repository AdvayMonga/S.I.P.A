import type { ComponentType } from "react";

import { Chat } from "../components/Chat";
import { AgentsModule } from "./Agents";
import { CostModule } from "./Cost";

/** A dashboard module = one capability's tile. `w`/`h` are its footprint in grid units (cols=12).
 * Each capability gets its own component, built individually; placeholders until their data exists. */
export type Module = { id: string; title: string; w: number; h: number; Component: ComponentType };

function Placeholder({ note }: { note: string }) {
  return <p className="module-empty">{note}</p>;
}

const SchedulerModule = () => <Placeholder note="scheduled tasks — not wired yet" />;

export const MODULES: Module[] = [
  { id: "chat", title: "Chat", w: 7, h: 12, Component: Chat },
  { id: "cost", title: "Token Usage", w: 5, h: 4, Component: CostModule },
  { id: "agents", title: "Background Agents", w: 5, h: 4, Component: AgentsModule },
  { id: "scheduler", title: "Scheduler", w: 5, h: 4, Component: SchedulerModule },
];

// Default arrangement (chat large on the left; capability tiles stacked on the right).
export const DEFAULT_LAYOUT = [
  { i: "chat", x: 0, y: 0, w: 7, h: 12 },
  { i: "cost", x: 7, y: 0, w: 5, h: 4 },
  { i: "agents", x: 7, y: 4, w: 5, h: 4 },
  { i: "scheduler", x: 7, y: 8, w: 5, h: 4 },
];
