import { useState } from "react";

import { Dashboard } from "./components/Dashboard";
import { StatusBar } from "./components/StatusBar";
import { BusyProvider } from "./state";
import { TelemetryProvider } from "./telemetry";

export function App() {
  const [editing, setEditing] = useState(false);
  return (
    <BusyProvider>
      <TelemetryProvider>
        <div className="app">
          <StatusBar editing={editing} onToggleEdit={() => setEditing((e) => !e)} />
          <Dashboard editing={editing} />
        </div>
      </TelemetryProvider>
    </BusyProvider>
  );
}
