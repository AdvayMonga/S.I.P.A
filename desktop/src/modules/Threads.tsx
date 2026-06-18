import type { MouseEvent } from "react";

import { useThreads } from "../threads";

/** The switchboard panel — every thread as a slot: status dot (running pulses, ready glows, idle
 * dim), label, and a per-state control (Stop while running, else Resolve). Click a slot to swap it
 * into the focused chat. "+ new thread" spins up another, up to 5. See design/concurrent-chats.md. */
export function ThreadsModule() {
  const { threads, focused, unread, swap, newThread, stop, resolve } = useThreads();

  const hit = (e: MouseEvent, fn: () => void) => {
    e.stopPropagation(); // don't let the button click also swap the slot
    fn();
  };

  return (
    <div className="threads">
      <ul className="thread-list">
        {threads.map((t) => {
          const isFocused = t.id === focused;
          const state =
            t.status === "running"
              ? "running"
              : unread.has(t.id) && !isFocused
                ? "ready"
                : "idle";
          return (
            <li
              key={t.id}
              className={`thread ${isFocused ? "thread--focused" : ""}`}
              onClick={() => swap(t.id)}
            >
              <span className={`thread-dot thread-dot--${state}`} />
              <span className="thread-label">{t.label || "(new thread)"}</span>
              {t.status === "running" ? (
                <button className="thread-act stop" onClick={(e) => hit(e, () => stop(t.id))}>
                  stop
                </button>
              ) : (
                <button className="thread-act" onClick={(e) => hit(e, () => resolve(t.id))}>
                  resolve
                </button>
              )}
            </li>
          );
        })}
      </ul>
      <button className="thread-new" onClick={() => newThread()} disabled={threads.length >= 5}>
        + new thread
      </button>
    </div>
  );
}
