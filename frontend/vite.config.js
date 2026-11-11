import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
// Im Entwicklungsmodus leitet Vite /api an das lokale Backend weiter
export default defineConfig({ plugins: [react()], server: { proxy: { "/api": { target: "http://localhost:8000", rewrite: p => p.replace(/^\/api/, "") } } } });
