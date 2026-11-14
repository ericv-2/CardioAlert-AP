import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// La web llama a /api/...; en desarrollo Vite lo reenvía a la API de FastAPI (puerto 8000).
const API = process.env.VITE_API_PROXY || "http://127.0.0.1:8000";

const proxy = { "/api": { target: API, changeOrigin: true }, "/cds-services": { target: API, changeOrigin: true } };

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, proxy },
  preview: { port: 4173, proxy },
});
