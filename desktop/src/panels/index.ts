import type { ComponentType } from "react";

import { AutobuildBody } from "./AutobuildPanel";
import { CostBody } from "./CostPanel";
import { TasksBody } from "./TasksPanel";

export type PanelDef = { id: string; title: string; Body: ComponentType };

/** The configurable dashboard panels. Today these render placeholder/empty states; each gets a
 * live data source later (cost + tasks are cheap to wire; autobuild waits on siloop). */
export const PANELS: PanelDef[] = [
  { id: "cost", title: "Cost", Body: CostBody },
  { id: "tasks", title: "Open Tasks", Body: TasksBody },
  { id: "autobuild", title: "Autobuild", Body: AutobuildBody },
];
