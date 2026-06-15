import { useState } from "react";

import { Chat } from "./components/Chat";
import { PanelGrid } from "./components/PanelGrid";
import { StatusBar } from "./components/StatusBar";
import { PANELS } from "./panels";

export function App() {
  const [busy, setBusy] = useState(false);
  return (
    <div className="app">
      <StatusBar state={busy ? "active" : "idle"} />
      <PanelGrid panels={PANELS} />
      <Chat onBusyChange={setBusy} />
    </div>
  );
}
