import type { ReactNode } from "react";

/** A module's frame: a title bar (the drag handle in edit mode) + body. */
export function Tile({
  title,
  editing,
  onRemove,
  children,
}: {
  title: string;
  editing: boolean;
  onRemove: () => void;
  children: ReactNode;
}) {
  return (
    <div className={`tile ${editing ? "tile--editing" : ""}`}>
      <div className="tile-head">
        <span className="tile-title">{title}</span>
        {editing && (
          <button className="tile-remove" onClick={onRemove} title="remove">
            ×
          </button>
        )}
      </div>
      <div className="tile-body">{children}</div>
    </div>
  );
}
