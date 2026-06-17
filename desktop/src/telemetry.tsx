import { listen } from "@tauri-apps/api/event";
import { createContext, type ReactNode, useContext, useEffect, useState } from "react";

// One listener for all `sipa-telemetry` snapshots, holding the latest payload per `topic`. Modules
// read their slice via useTelemetry("cost" | "agents" | …) — no per-module socket, route by topic.
type Snapshot = Record<string, unknown> & { topic: string };
const TelemetryContext = createContext<Record<string, Snapshot>>({});

export function TelemetryProvider({ children }: { children: ReactNode }) {
  const [byTopic, setByTopic] = useState<Record<string, Snapshot>>({});
  useEffect(() => {
    const unlisten = listen<Snapshot>("sipa-telemetry", (e) => {
      setByTopic((s) => ({ ...s, [e.payload.topic]: e.payload }));
    });
    return () => {
      unlisten.then((off) => off());
    };
  }, []);
  return <TelemetryContext.Provider value={byTopic}>{children}</TelemetryContext.Provider>;
}

export function useTelemetry<T = Snapshot>(topic: string): T | undefined {
  return useContext(TelemetryContext)[topic] as T | undefined;
}
