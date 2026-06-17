import "@fontsource-variable/jetbrains-mono";
import "@fontsource-variable/public-sans";

import ReactDOM from "react-dom/client";

import { App } from "./App";
import "./styles/global.css";
import "./styles/dashboard.css";

// No React.StrictMode: its dev double-mount leaves react-grid-layout's drag (react-draggable via
// findDOMNode) bound to a detached node, so tiles won't drag. See design/dashboard.md.
ReactDOM.createRoot(document.getElementById("root")!).render(<App />);
