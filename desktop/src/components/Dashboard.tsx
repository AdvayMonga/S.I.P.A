import { useEffect, useState } from "react";
import GridLayout, { type Layout, WidthProvider } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";

import { DEFAULT_LAYOUT, MODULES } from "../modules/registry";
import { Tile } from "./Tile";

const Grid = WidthProvider(GridLayout);
const STORE_KEY = "sipa.dashboard.v2";

type Saved = { layout: Layout[]; enabled: string[] };

function load(): Saved {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) return JSON.parse(raw) as Saved;
  } catch {
    /* fall through to default */
  }
  return { layout: DEFAULT_LAYOUT, enabled: MODULES.map((m) => m.id) };
}

/** The customizable module grid. Drag-to-place (snap to grid) in edit mode; fixed footprints; the
 * single layout persists to localStorage across sessions. See design/dashboard.md. */
export function Dashboard({ editing }: { editing: boolean }) {
  const [{ layout, enabled }, setState] = useState<Saved>(load);

  useEffect(() => {
    localStorage.setItem(STORE_KEY, JSON.stringify({ layout, enabled }));
  }, [layout, enabled]);

  const placed = MODULES.filter((m) => enabled.includes(m.id));
  const available = MODULES.filter((m) => !enabled.includes(m.id));

  // Guarantee a layout entry per placed module (RGL needs one); missing → auto-place at the bottom.
  const fullLayout: Layout[] = placed.map(
    (m) => layout.find((l) => l.i === m.id) ?? { i: m.id, x: 0, y: Infinity, w: m.w, h: m.h },
  );

  const remove = (id: string) =>
    setState((s) => ({
      layout: s.layout.filter((l) => l.i !== id),
      enabled: s.enabled.filter((e) => e !== id),
    }));

  const add = (id: string) =>
    setState((s) => ({ ...s, enabled: [...s.enabled, id] }));

  return (
    <div className="dashboard">
      {editing && (
        <div className="add-bar">
          <span className="add-label">add module:</span>
          {available.length > 0 ? (
            available.map((m) => (
              <button key={m.id} onClick={() => add(m.id)}>
                {m.title}
              </button>
            ))
          ) : (
            <span className="add-empty">all modules placed</span>
          )}
        </div>
      )}
      <Grid
        className="grid"
        layout={fullLayout}
        cols={12}
        rowHeight={36}
        margin={[10, 10]}
        isResizable={false}
        isDraggable={editing}
        draggableHandle=".tile-head"
        draggableCancel=".tile-remove"
        onLayoutChange={(l: Layout[]) => setState((s) => ({ ...s, layout: l }))}
      >
        {placed.map((m) => (
          <div key={m.id}>
            <Tile title={m.title} editing={editing} onRemove={() => remove(m.id)}>
              <m.Component />
            </Tile>
          </div>
        ))}
      </Grid>
    </div>
  );
}
