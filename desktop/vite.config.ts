import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Tauri serves the frontend from this dev server (devUrl) in dev and from dist/ in build.
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: { port: 5173, strictPort: true },
  // react-draggable (bundled in react-grid-layout) reads process.env.DRAGGABLE_DEBUG, which throws
  // "process is not defined" in the browser and kills drag-start. Neutralize that one access.
  define: { "process.env.DRAGGABLE_DEBUG": "false" },
});
