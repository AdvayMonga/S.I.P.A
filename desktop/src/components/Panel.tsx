import type { ReactNode } from "react";

export function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <article className="panel">
      <h2 className="panel-title">{title}</h2>
      <div className="panel-body">{children}</div>
    </article>
  );
}
