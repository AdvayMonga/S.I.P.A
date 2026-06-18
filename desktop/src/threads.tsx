import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { createContext, type ReactNode, useContext, useEffect, useRef, useState } from "react";

export type ThreadMeta = { id: string; label: string; status: "idle" | "running" };
export type Msg = { role: "user" | "sipa"; text: string };
type Approval = { id: string; question: string };

// The switchboard's client state: the pool's thread list + per-thread transcripts, which thread is
// focused, and which have unread results. The list is fetched on mount (reliable initial state) and
// then kept current by pushed deltas; replies and approvals arrive as pushed events tagged by thread,
// so they route to the right thread even after you've swapped away.
type ThreadsCtx = {
  threads: ThreadMeta[];
  focused: string | null;
  transcript: Msg[]; // the focused thread's messages
  pending: boolean; // focused thread is awaiting a reply
  unread: Set<string>;
  approval: Approval | null; // focused thread's pending mid-turn question
  send: (text: string) => Promise<void>;
  swap: (id: string) => void;
  newThread: () => Promise<void>;
  background: () => Promise<void>;
  stop: (id: string) => Promise<void>;
  resolve: (id: string) => Promise<void>;
  merge: (sourceId: string) => Promise<void>;
  answerApproval: (answer: string) => Promise<void>;
};

const Ctx = createContext<ThreadsCtx>(null as unknown as ThreadsCtx);

export function ThreadsProvider({ children }: { children: ReactNode }) {
  const [threads, setThreads] = useState<ThreadMeta[]>([]);
  const [focused, setFocused] = useState<string | null>(null);
  const [transcripts, setTranscripts] = useState<Record<string, Msg[]>>({});
  const [pendingSet, setPendingSet] = useState<Set<string>>(new Set());
  const [unread, setUnread] = useState<Set<string>>(new Set());
  const [approvals, setApprovals] = useState<Record<string, Approval>>({});

  const focusedRef = useRef<string | null>(null);
  focusedRef.current = focused;
  const threadsRef = useRef<ThreadMeta[]>([]);

  // Fetch the initial thread list, retrying until the daemon is reachable (it may still be starting).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      while (!cancelled) {
        try {
          const snap = JSON.parse(await invoke<string>("snapshot")) as { threads: ThreadMeta[] };
          if (!cancelled) setThreads(snap.threads);
          return;
        } catch {
          await new Promise((r) => setTimeout(r, 1000));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    threadsRef.current = threads;
    setTranscripts((t) => {
      const next = { ...t };
      for (const th of threads) if (!(th.id in next)) next[th.id] = [];
      return next;
    });
    // Keep focus on a thread that still exists; if the focused one was resolved, move to another.
    setFocused((f) => (f && threads.some((th) => th.id === f) ? f : (threads[0]?.id ?? null)));
  }, [threads]);

  function append(id: string, msg: Msg) {
    setTranscripts((t) => ({ ...t, [id]: [...(t[id] ?? []), msg] }));
  }

  function clearPending(id: string) {
    setPendingSet((p) => {
      const n = new Set(p);
      n.delete(id);
      return n;
    });
  }

  // A reply arrived for thread `id`: append it, clear its pending, mark unread if you've moved on.
  function deliver(id: string, msg: Msg) {
    append(id, msg);
    clearPending(id);
    if (focusedRef.current !== id) setUnread((u) => new Set(u).add(id));
  }

  // Pushed events: the thread-list delta (state) + per-thread replies and approvals (discrete).
  useEffect(() => {
    type Ev = {
      topic: string;
      threads?: ThreadMeta[];
      thread?: string;
      text?: string;
      id?: string;
      question?: string;
    };
    const un = listen<Ev>("sipa-telemetry", (e) => {
      const ev = e.payload;
      if (ev.topic === "threads") setThreads(ev.threads ?? []);
      else if (ev.topic === "reply") deliver(ev.thread!, { role: "sipa", text: ev.text ?? "" });
      else if (ev.topic === "approval")
        setApprovals((a) => ({ ...a, [ev.thread!]: { id: ev.id!, question: ev.question! } }));
    });
    return () => {
      un.then((off) => off());
    };
  }, []);

  // Proactive plain pushes (scheduled tasks etc.) land on the main (lowest-id) thread.
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
      await invoke("send", { threadId: target, message: text }); // fire-and-forget; reply via push
    } catch (err) {
      deliver(target, { role: "sipa", text: `[error] ${err}` });
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

  // Hand the focused thread's running turn to a new thread; stay here, keep chatting.
  async function background() {
    const a = focusedRef.current;
    if (!a || !pendingSet.has(a)) return;
    const bid = await invoke<string>("background_thread", { id: a });
    if (!bid) return;
    // Mirror the backend hand-off: move the in-flight request (trailing user msg) from A to B.
    setTranscripts((t) => {
      const aMsgs = t[a] ?? [];
      const idx = aMsgs.map((m) => m.role).lastIndexOf("user");
      if (idx < 0) return t;
      return { ...t, [a]: aMsgs.slice(0, idx), [bid]: [...(t[bid] ?? []), ...aMsgs.slice(idx)] };
    });
    clearPending(a);
    setPendingSet((p) => new Set(p).add(bid));
  }

  const stop = (id: string) => invoke("stop_thread", { id }).then(() => {});
  const resolve = (id: string) => invoke("resolve_thread", { id }).then(() => {});

  // Fold a side thread's findings into the focused thread (the note arrives as a tagged reply).
  async function merge(sourceId: string) {
    const target = focusedRef.current;
    if (!target || sourceId === target) return;
    await invoke("merge_thread", { source: sourceId, target });
  }

  async function answerApproval(answer: string) {
    const id = focusedRef.current;
    const appr = id ? approvals[id] : null;
    if (!id || !appr) return;
    setApprovals((a) => {
      const n = { ...a };
      delete n[id];
      return n;
    });
    await invoke("answer_approval", { id: appr.id, answer });
  }

  const value: ThreadsCtx = {
    threads,
    focused,
    transcript: (focused && transcripts[focused]) || [],
    pending: focused ? pendingSet.has(focused) : false,
    unread,
    approval: (focused && approvals[focused]) || null,
    send,
    swap,
    newThread,
    background,
    stop,
    resolve,
    merge,
    answerApproval,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useThreads = () => useContext(Ctx);
