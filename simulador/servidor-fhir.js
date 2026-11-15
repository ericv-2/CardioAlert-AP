// Servidor FHIR R4 mínimo de la estación clínica simulada (plugin de Vite, solo lectura).
//
//   GET /fhir/metadata                    CapabilityStatement resumido
//   GET /fhir/Patient                     Bundle "searchset" con los pacientes del cupo
//   GET /fhir/Patient/{id}/$everything    Bundle con toda la historia del paciente
//
// Lee una carpeta con un Bundle JSON por paciente (los datos sintéticos del repo). Es la historia clínica
// PROPIA de la estación: funciona igual con el add-on instalado o sin él.
import fs from "node:fs";
import path from "node:path";

export default function servidorFhir(carpeta) {
  let indice = null; // id de paciente -> { fichero, paciente }; se construye en la primera petición

  function cargarIndice() {
    if (indice) return indice;
    if (!fs.existsSync(carpeta)) throw new Error(`No existe la carpeta de datos ${carpeta}. Ejecute: python scripts/generate_patients.py`);
    indice = new Map();
    let fecha = null;
    for (const nombre of fs.readdirSync(carpeta).filter((f) => f.endsWith(".json")).sort()) {
      const fichero = path.join(carpeta, nombre);
      const bundle = JSON.parse(fs.readFileSync(fichero, "utf-8"));
      const paciente = bundle.entry?.map((e) => e.resource).find((r) => r?.resourceType === "Patient");
      if (!paciente) continue;
      indice.set(paciente.id, { fichero, paciente });
      if (bundle.timestamp && (!fecha || bundle.timestamp > fecha)) fecha = bundle.timestamp;
    }
    indice.fecha = fecha; // la "fecha de hoy" de la simulación: la de extracción de los datos
    return indice;
  }

  function responder(res, estado, cuerpo) {
    res.statusCode = estado;
    res.setHeader("Content-Type", "application/fhir+json; charset=utf-8");
    res.setHeader("Cache-Control", "no-store");
    res.end(typeof cuerpo === "string" ? cuerpo : JSON.stringify(cuerpo));
  }

  const error = (res, estado, texto) =>
    responder(res, estado, { resourceType: "OperationOutcome", issue: [{ severity: "error", code: estado === 404 ? "not-found" : "exception", diagnostics: texto }] });

  function atender(req, res) {
    const ruta = decodeURIComponent(new URL(req.url, "http://localhost").pathname).replace(/\/+$/, "");
    if (req.method !== "GET") return error(res, 405, "Servidor de solo lectura");
    try {
      if (ruta === "/metadata") {
        return responder(res, 200, {
          resourceType: "CapabilityStatement",
          status: "active",
          kind: "instance",
          fhirVersion: "4.0.1",
          format: ["json"],
          software: { name: "Estación clínica simulada (datos sintéticos)" },
          rest: [{ mode: "server", resource: [{ type: "Patient", interaction: [{ code: "search-type" }], operation: [{ name: "everything" }] }] }],
        });
      }
      const idx = cargarIndice();
      if (ruta === "/Patient") {
        return responder(res, 200, {
          resourceType: "Bundle",
          type: "searchset",
          timestamp: idx.fecha,
          total: idx.size,
          entry: [...idx.values()].map(({ paciente }) => ({ resource: paciente })),
        });
      }
      const m = ruta.match(/^\/Patient\/([^/]+)\/\$everything$/);
      if (m) {
        const ficha = idx.get(m[1]);
        if (!ficha) return error(res, 404, `Paciente ${m[1]} no encontrado`);
        return responder(res, 200, fs.readFileSync(ficha.fichero, "utf-8"));
      }
      return error(res, 404, `Ruta no soportada: ${ruta}`);
    } catch (e) {
      return error(res, 500, e.message);
    }
  }

  return {
    name: "servidor-fhir-simulado",
    configureServer(server) {
      server.middlewares.use("/fhir", atender);
    },
    configurePreviewServer(server) {
      server.middlewares.use("/fhir", atender);
    },
  };
}
