import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
// Im Entwicklungsmodus leitet Vite /api an das lokale Backend weiter; Tests (vitest) laufen in jsdom
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": { target: "http://localhost:8000", rewrite: p => p.replace(/^\/api/, "") } } },
  test: { environment: "jsdom" },
});
