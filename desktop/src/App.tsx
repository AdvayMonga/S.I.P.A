import { Chat } from "./components/Chat";
import { PanelGrid } from "./components/PanelGrid";
import { StatusBar } from "./components/StatusBar";
import { PANELS } from "./panels";

export function App() {
  return (
    <div className="app">
      <StatusBar state="idle" />
      <PanelGrid panels={PANELS} />
      <Chat />
    </div>
  );
}
