import type { PanelDef } from "../panels";
import { Panel } from "./Panel";

/** Renders the configurable set of dashboard panels. Add/remove/reorder via the PANELS registry. */
export function PanelGrid({ panels }: { panels: PanelDef[] }) {
  return (
    <section className="panel-grid">
      {panels.map(({ id, title, Body }) => (
        <Panel key={id} title={title}>
          <Body />
        </Panel>
      ))}
    </section>
  );
}
