import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import servidorFhir from "./servidor-fhir.js";

// SIMULADOR: estación clínica genérica de una comunidad (puerto 5174). Es una aplicación independiente del
// add-on CardioAlert AP: tiene su propia historia clínica (servidor FHIR simulado en /fhir) y solo habla con
// el add-on por estándares (CDS Hooks y un lanzamiento SMART on FHIR simulado) cuando el add-on está instalado.
const AQUI = path.dirname(fileURLToPath(import.meta.url));
// Datos de la estación: los bundles FHIR sintéticos del repo (SIMULADOR_DATOS para usar otra carpeta)
const DATOS = process.env.SIMULADOR_DATOS || path.resolve(AQUI, "../data/synthetic/fhir");

export default defineConfig({
  plugins: [react(), tailwindcss(), servidorFhir(DATOS)],
  clearScreen: false,
  server: { port: 5174, strictPort: true },
  preview: { port: 5174, strictPort: true },
});
