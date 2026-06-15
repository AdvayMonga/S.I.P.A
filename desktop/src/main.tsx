import "@fontsource-variable/jetbrains-mono";
import "@fontsource-variable/public-sans";

import React from "react";
import ReactDOM from "react-dom/client";

import { App } from "./App";
import "./styles/global.css";
import "./styles/dashboard.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
