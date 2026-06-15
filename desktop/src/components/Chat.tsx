/** Chat shell — static for now; the `ask` round-trip + live state pulse are wired in the next pass. */
export function Chat() {
  return (
    <>
      <section className="transcript">
        <p className="hint">Message S.I.P.A. to begin.</p>
      </section>
      <form className="composer" onSubmit={(e) => e.preventDefault()}>
        <input className="composer-input" placeholder="message S.I.P.A." autoComplete="off" />
        <button className="composer-send" type="submit">
          send
        </button>
      </form>
    </>
  );
}
