import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { type FormEvent, useEffect, useRef, useState } from "react";

type Msg = { role: "user" | "sipa"; text: string };

/** Chat over the daemon socket. `onBusyChange` drives the status-bar state pulse: warm while a
 * request is in flight (the bot is actually thinking), cool otherwise. */
export function Chat({ onBusyChange }: { onBusyChange: (busy: boolean) => void }) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pending]);

  // Proactive messages the daemon pushes on its own (background results, scheduled tasks).
  useEffect(() => {
    const unlisten = listen<string>("sipa-push", (e) => {
      setMessages((m) => [...m, { role: "sipa", text: e.payload }]);
    });
    return () => {
      unlisten.then((off) => off());
    };
  }, []);

  async function send(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || pending) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text }]);
    setPending(true);
    onBusyChange(true);
    try {
      const reply = await invoke<string>("ask", { message: text });
      setMessages((m) => [...m, { role: "sipa", text: reply }]);
    } catch (err) {
      setMessages((m) => [...m, { role: "sipa", text: `[error] ${err}` }]);
    } finally {
      setPending(false);
      onBusyChange(false);
    }
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
