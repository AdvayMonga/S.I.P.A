import { useState } from "react";

import { Dashboard } from "./components/Dashboard";
import { StatusBar } from "./components/StatusBar";
import { BusyProvider } from "./state";
import { TelemetryProvider } from "./telemetry";
import { ThreadsProvider } from "./threads";

export function App() {
  const [editing, setEditing] = useState(false);
  return (
    <BusyProvider>
      <TelemetryProvider>
        <ThreadsProvider>
          <div className="app">
            <StatusBar editing={editing} onToggleEdit={() => setEditing((e) => !e)} />
            <Dashboard editing={editing} />
          </div>
        </ThreadsProvider>
      </TelemetryProvider>
    </BusyProvider>
  );
}
