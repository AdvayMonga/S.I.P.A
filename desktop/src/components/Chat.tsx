import { type FormEvent, useEffect, useRef, useState } from "react";

import { useBusy } from "../state";
import { useThreads } from "../threads";

/** Chat with the focused thread. Transcript, send, and approvals live in the threads store (so they
 * route per thread across swaps); this is the focused thread's view. The main module. */
export function Chat() {
  const { setBusy } = useBusy();
  const { transcript, pending, send: sendThread, focused, approval, answerApproval, background } =
    useThreads();
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const messages = transcript;

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pending]);

  useEffect(() => {
    setBusy(pending);
  }, [pending, setBusy]);

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
        {pending && (
          <div className="working">
            <span className="bubble bubble--sipa pending">…</span>
            <button className="to-bg" onClick={() => background()}>
              ⤳ send to background
            </button>
          </div>
        )}
        {approval && (
          <div className="approval">
            <div className="approval-q">⚠ {approval.question}</div>
            <div className="approval-actions">
              <button onClick={() => answerApproval("y")}>Approve</button>
              <button onClick={() => answerApproval("a")}>Always</button>
              <button className="deny" onClick={() => answerApproval("n")}>
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
