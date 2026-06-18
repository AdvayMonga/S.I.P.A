import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { createContext, type ReactNode, useContext, useEffect, useRef, useState } from "react";

import { useTelemetry } from "./telemetry";

export type ThreadMeta = { id: string; label: string; status: "idle" | "running" };
export type Msg = { role: "user" | "sipa"; text: string };

// The switchboard's client state: the pool's thread list (from telemetry) + per-thread transcripts,
// which thread is focused, and which have unread results. Lives above Chat so a reply routes to the
// thread it was sent to even after you've swapped away. See design/concurrent-chats.md.
type ThreadsCtx = {
  threads: ThreadMeta[];
  focused: string | null;
  transcript: Msg[]; // the focused thread's messages
  pending: boolean; // focused thread is awaiting a reply
  unread: Set<string>;
  send: (text: string) => Promise<void>;
  swap: (id: string) => void;
  newThread: () => Promise<void>;
  stop: (id: string) => Promise<void>;
  resolve: (id: string) => Promise<void>;
};

const Ctx = createContext<ThreadsCtx>(null as unknown as ThreadsCtx);

export function ThreadsProvider({ children }: { children: ReactNode }) {
  const snap = useTelemetry<{ threads: ThreadMeta[] }>("threads");
  const threads = snap?.threads ?? [];
  const [focused, setFocused] = useState<string | null>(null);
  const [transcripts, setTranscripts] = useState<Record<string, Msg[]>>({});
  const [pendingSet, setPendingSet] = useState<Set<string>>(new Set());
  const [unread, setUnread] = useState<Set<string>>(new Set());

  const focusedRef = useRef<string | null>(null);
  focusedRef.current = focused;
  const threadsRef = useRef<ThreadMeta[]>([]);

  // On each thread snapshot: seed transcripts for new ids, keep focus valid.
  useEffect(() => {
    const list = snap?.threads ?? [];
    threadsRef.current = list;
    if (list.length === 0) return;
    setTranscripts((t) => {
      const next = { ...t };
      for (const th of list) if (!(th.id in next)) next[th.id] = [];
      return next;
    });
    setFocused((f) => (f && list.some((th) => th.id === f) ? f : list[0].id));
  }, [snap]);

  function append(id: string, msg: Msg) {
    setTranscripts((t) => ({ ...t, [id]: [...(t[id] ?? []), msg] }));
  }

  // A reply arrived for thread `id`: append it, and mark unread if you've since looked elsewhere.
  function deliver(id: string, msg: Msg) {
    append(id, msg);
    if (focusedRef.current !== id) setUnread((u) => new Set(u).add(id));
  }

  // Proactive pushes (background results, scheduled tasks) land on the main (lowest-id) thread.
  useEffect(() => {
    const un = listen<string>("sipa-push", (e) => {
      const ids = threadsRef.current.map((t) => t.id).sort((a, b) => +a - +b);
      if (ids.length) deliver(ids[0], { role: "sipa", text: e.payload });
    });
    return () => {
      un.then((off) => off());
    };
  }, []);

  async function send(text: string) {
    const target = focusedRef.current;
    if (!target) return;
    append(target, { role: "user", text });
    setPendingSet((p) => new Set(p).add(target));
    try {
      const reply = await invoke<string>("ask", { threadId: target, message: text });
      deliver(target, { role: "sipa", text: reply });
    } catch (err) {
      deliver(target, { role: "sipa", text: `[error] ${err}` });
    } finally {
      setPendingSet((p) => {
        const n = new Set(p);
        n.delete(target);
        return n;
      });
    }
  }

  function swap(id: string) {
    setFocused(id);
    setUnread((u) => {
      const n = new Set(u);
      n.delete(id);
      return n;
    });
  }

  async function newThread() {
    const id = await invoke<string>("new_thread");
    setTranscripts((t) => ({ ...t, [id]: t[id] ?? [] }));
    swap(id);
  }

  const stop = (id: string) => invoke("stop_thread", { id }).then(() => {});
  const resolve = (id: string) => invoke("resolve_thread", { id }).then(() => {});

  const value: ThreadsCtx = {
    threads,
    focused,
    transcript: (focused && transcripts[focused]) || [],
    pending: focused ? pendingSet.has(focused) : false,
    unread,
    send,
    swap,
    newThread,
    stop,
    resolve,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useThreads = () => useContext(Ctx);
