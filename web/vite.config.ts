import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// En desarrollo, Vite (5173) reenvía /api a la API de Python (8000).
export default defineConfig({
  plugins: [vue()],
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
