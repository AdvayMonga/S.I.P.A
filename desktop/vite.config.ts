import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Tauri serves the frontend from this dev server (devUrl) in dev and from dist/ in build.
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: { port: 5173, strictPort: true },
});
