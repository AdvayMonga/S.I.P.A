const { invoke } = window.__TAURI__.core;

const log = document.querySelector("#log");
const composer = document.querySelector("#composer");
const input = document.querySelector("#msg");

function bubble(text, who) {
  const el = document.createElement("div");
  el.className = `bubble ${who}`;
  el.textContent = text;
  log.appendChild(el);
  log.scrollTop = log.scrollHeight;
  return el;
}

composer.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  bubble(text, "user");
  const pending = bubble("…", "sipa");
  try {
    pending.textContent = await invoke("ask", { message: text });
  } catch (err) {
    pending.textContent = `[error] ${err}`;
  }
});
