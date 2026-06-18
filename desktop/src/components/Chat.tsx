import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { type FormEvent, useEffect, useRef, useState } from "react";

import { useBusy } from "../state";
import { useThreads } from "../threads";

/** Chat with the focused thread. Transcript + send live in the threads store (so replies route per
 * thread across swaps); this is the focused thread's view. The main module on the dashboard. */
export function Chat() {
  const { setBusy } = useBusy();
  const { transcript, pending, send: sendThread, focused } = useThreads();
  const [input, setInput] = useState("");
  const [approval, setApproval] = useState<{ id: string; question: string } | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const messages = transcript;

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pending]);

  useEffect(() => {
    setBusy(pending);
  }, [pending, setBusy]);

  // Mid-turn approval questions (e.g. before running a shell command).
  useEffect(() => {
    const unlisten = listen<{ id: string; question: string }>("approval-request", (e) => {
      setApproval(e.payload);
    });
    return () => {
      unlisten.then((off) => off());
    };
  }, []);

  async function answer(id: string, choice: string) {
    setApproval(null);
    await invoke("approve", { id, answer: choice });
  }

  async function send(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || pending || !focused) return;
    setInput("");
    await sendThread(text);
  }

  return (
    <>
      <section className="transcript">
        {messages.length === 0 && !pending ? (
          <p className="hint">Message S.I.P.A. to begin.</p>
        ) : (
          messages.map((m, i) => (
            <div key={i} className={`bubble bubble--${m.role}`}>
              {m.text}
            </div>
          ))
        )}
        {pending && <div className="bubble bubble--sipa pending">…</div>}
        {approval && (
          <div className="approval">
            <div className="approval-q">⚠ {approval.question}</div>
            <div className="approval-actions">
              <button onClick={() => answer(approval.id, "y")}>Approve</button>
              <button onClick={() => answer(approval.id, "a")}>Always</button>
              <button className="deny" onClick={() => answer(approval.id, "n")}>
                Deny
              </button>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </section>
      <form className="composer" onSubmit={send}>
        <input
          className="composer-input"
          placeholder="message S.I.P.A."
          autoComplete="off"
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button className="composer-send" type="submit" disabled={pending}>
          send
        </button>
      </form>
    </>
  );
}
