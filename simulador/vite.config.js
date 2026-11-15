import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import servidorFhir, { DATOS_POR_DEFECTO } from "./servidor-fhir.js";

// SIMULADOR: estación clínica genérica de una comunidad (puerto 5174). Es una aplicación independiente del
// add-on CardioAlert AP: tiene su propia historia clínica (servidor FHIR en /fhir) y solo habla con el add-on
// por estándares (CDS Hooks, lanzamiento SMART on FHIR simulado y FHIR Bulk Data) cuando el add-on está instalado.
//
// Los datos de los pacientes son de la estación: simulador/datos/<cupo>/fhir (SIMULADOR_DATOS para usar otra
// carpeta; SIMULADOR_CUPO = demo | realista para el cupo activo al arrancar).
const datos = process.env.SIMULADOR_DATOS ? path.resolve(process.env.SIMULADOR_DATOS) : DATOS_POR_DEFECTO;
const vigilancia = { ignored: ["**/datos/**"] }; // 1.600 bundles: no hace falta vigilar sus cambios

export default defineConfig({
  plugins: [react(), tailwindcss(), servidorFhir({ datos, cupoInicial: process.env.SIMULADOR_CUPO || "demo" })],
  clearScreen: false,
  server: { port: 5174, strictPort: true, watch: vigilancia },
  preview: { port: 5174, strictPort: true },
});
