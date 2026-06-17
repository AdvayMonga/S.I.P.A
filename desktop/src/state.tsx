import { createContext, type ReactNode, useContext, useState } from "react";

// Shared "is the bot working" flag — set by Chat, read by the status-bar pulse — so modules stay
// uniform (no prop threading through the grid).
const BusyContext = createContext<{ busy: boolean; setBusy: (b: boolean) => void }>({
  busy: false,
  setBusy: () => {},
});

export function BusyProvider({ children }: { children: ReactNode }) {
  const [busy, setBusy] = useState(false);
  return <BusyContext.Provider value={{ busy, setBusy }}>{children}</BusyContext.Provider>;
}

export const useBusy = () => useContext(BusyContext);
