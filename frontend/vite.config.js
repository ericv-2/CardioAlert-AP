import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Interfaz del ADD-ON CardioAlert AP (puerto 5173). Llama a /api/... y Vite lo reenvía a la API (puerto 8000).
// La estación clínica simulada es otra aplicación (carpeta simulador/, puerto 5174).
const API = process.env.VITE_API_PROXY || "http://127.0.0.1:8000";

const proxy = { "/api": { target: API, changeOrigin: true } };

export default defineConfig({
  plugins: [react(), tailwindcss()],
  clearScreen: false, // no borra las URL que imprime start_addon
  // Puerto fijo: es la URL que la API anuncia a la estación clínica (CARDIOALERT_UI_URL)
  server: { port: 5173, strictPort: true, proxy },
  preview: { port: 5173, strictPort: true, proxy },
});
