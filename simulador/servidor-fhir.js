// Servidor FHIR R4 de la estación clínica simulada (solo lectura, sin dependencias: solo Node).
//
// Los datos de los pacientes son de la ESTACIÓN (carpeta simulador/datos, un Bundle JSON por paciente). El
// add-on no tiene datos propios: los lee de aquí, igual que leería los de una estación clínica real.
//
//   GET /fhir/metadata                          CapabilityStatement
//   GET /fhir/Patient[?name=&_id=&_count=]      búsqueda de pacientes del cupo activo (Bundle "searchset")
//   GET /fhir/Patient/{id}                      un paciente
//   GET /fhir/Patient/{id}/$everything          Bundle con toda la historia del paciente
//   GET /fhir/Group                             el cupo activo como recurso Group (sin miembros)
//   GET /fhir/Group/{id}                        el cupo con sus miembros
//   GET /fhir/Group/{id}/$export                FHIR Bulk Data simplificado: 202 + Content-Location
//   GET /fhir/$export-status/{trabajo}          manifiesto de la exportación (un fichero NDJSON por tipo)
//   GET /fhir/$export-file/{trabajo}/{Tipo}.ndjson
//
// Bulk Data "simplificado": el flujo es el del estándar (arranque asíncrono, estado, manifiesto, NDJSON), pero
// la exportación termina al instante, no hay OAuth y no se puede cancelar.
//
// Fuera de FHIR, la estación tiene dos rutas de administración para elegir el cupo activo
// (Configuración → Cupo / centro):
//   GET  /estacion/cupos      cupos disponibles y cuál está activo
//   POST /estacion/cupo       { "id": "demo" | "realista" }
//
// Se usa de dos maneras: como plugin de Vite (en el puerto de la estación, 5174) o por su cuenta:
//   node servidor-fhir.js [--port 5174] [--datos carpeta] [--cupo demo|realista]
import crypto from "node:crypto";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

export const ESTACION = "Estación clínica simulada";
const AQUI = path.dirname(fileURLToPath(import.meta.url));
export const DATOS_POR_DEFECTO = path.join(AQUI, "datos");
const TIPOS = ["Patient", "Observation", "Condition", "MedicationStatement"];

// Cupos de la estación: cada uno es una carpeta de datos/ con los bundles en fhir/.
export const CUPOS = [
  {
    id: "demo",
    nombre: "Cupo demo",
    centro: "Consultorio de demostración",
    descripcion: "100 pacientes sintéticos, con los 8 casos de ejemplo (P001-P008).",
    generar: "python scripts/generate_patients.py",
  },
  {
    id: "realista",
    nombre: "Cupo realista",
    centro: "Centro de salud urbano",
    descripcion: "1.500 adultos sintéticos con prevalencias calibradas con REGICOR y ENRICA.",
    generar: "python scripts/generate_patients.py --perfil realista --n 1500",
  },
];

class ErrorHttp extends Error {
  constructor(estado, mensaje) {
    super(mensaje);
    this.estado = estado;
  }
}

const sinAcentos = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

export function crearEstacion({ datos = DATOS_POR_DEFECTO, cupoInicial = "demo" } = {}) {
  const indices = new Map(); // id de cupo -> índice (se construye la primera vez que se pide)
  let activo = CUPOS.some((c) => c.id === cupoInicial) ? cupoInicial : CUPOS[0].id;

  const carpetaDe = (cupo) => path.join(datos, cupo.id, "fhir");
  const ficherosDe = (cupo) => {
    const carpeta = carpetaDe(cupo);
    return fs.existsSync(carpeta) ? fs.readdirSync(carpeta).filter((f) => f.endsWith(".json")).sort() : [];
  };

  // Lee todos los bundles de un cupo una sola vez: pacientes, fecha de los datos, versión y los NDJSON de la
  // exportación (una línea por recurso). La historia de un paciente se sigue leyendo de su fichero.
  function cargar(id) {
    if (indices.has(id)) return indices.get(id);
    const cupo = CUPOS.find((c) => c.id === id);
    if (!cupo) throw new ErrorHttp(404, `Cupo ${id} desconocido`);
    const nombres = ficherosDe(cupo);
    if (nombres.length === 0) throw new ErrorHttp(503, `El ${cupo.nombre.toLowerCase()} no tiene datos en ${carpetaDe(cupo)}. Ejecute: ${cupo.generar}`);
    const pacientes = new Map();
    const lineas = Object.fromEntries(TIPOS.map((t) => [t, []]));
    const huella = crypto.createHash("sha1");
    let fecha = null;
    for (const nombre of nombres) {
      const fichero = path.join(carpetaDe(cupo), nombre);
      const texto = fs.readFileSync(fichero, "utf-8");
      huella.update(texto);
      const bundle = JSON.parse(texto);
      const recursos = (bundle.entry ?? []).map((e) => e.resource).filter(Boolean);
      const paciente = recursos.find((r) => r.resourceType === "Patient");
      if (!paciente) continue;
      pacientes.set(paciente.id, { fichero, paciente });
      for (const r of recursos) lineas[r.resourceType]?.push(JSON.stringify(r));
      if (bundle.timestamp && (!fecha || bundle.timestamp > fecha)) fecha = bundle.timestamp;
    }
    const indice = {
      cupo,
      grupoId: `cupo-${cupo.id}`,
      pacientes,
      fecha, // la "fecha de hoy" de la simulación: la de extracción de los datos
      version: huella.digest("hex").slice(0, 12), // cambia si cambian los datos
      ndjson: Object.fromEntries(TIPOS.map((t) => [t, { cuenta: lineas[t].length, datos: Buffer.from(lineas[t].map((l) => `${l}\n`).join(""), "utf-8") }])),
    };
    indices.set(id, indice);
    return indice;
  }

  const cargarActivo = () => cargar(activo);

  function grupo(indice, conMiembros) {
    const g = {
      resourceType: "Group",
      id: indice.grupoId,
      meta: { versionId: indice.version, lastUpdated: indice.fecha },
      type: "person",
      actual: true,
      active: true,
      name: indice.cupo.nombre,
      quantity: indice.pacientes.size,
      managingEntity: { display: indice.cupo.centro },
    };
    if (conMiembros) g.member = [...indice.pacientes.keys()].map((id) => ({ entity: { reference: `Patient/${id}` } }));
    return g;
  }

  function estadoCupos() {
    return {
      activo,
      cupos: CUPOS.map((c) => ({ id: c.id, nombre: c.nombre, centro: c.centro, descripcion: c.descripcion, generar: c.generar, pacientes: ficherosDe(c).length })),
    };
  }

  function responder(res, estado, cuerpo, tipo = "application/fhir+json; charset=utf-8", cabeceras = {}) {
    res.statusCode = estado;
    res.setHeader("Content-Type", tipo);
    res.setHeader("Cache-Control", "no-store");
    for (const [k, v] of Object.entries(cabeceras)) res.setHeader(k, v);
    res.end(cuerpo == null ? "" : typeof cuerpo === "string" || Buffer.isBuffer(cuerpo) ? cuerpo : JSON.stringify(cuerpo));
  }

  const CODIGO = { 400: "invalid", 404: "not-found", 405: "not-supported", 503: "transient" };
  const error = (res, estado, texto) =>
    responder(res, estado, { resourceType: "OperationOutcome", issue: [{ severity: "error", code: CODIGO[estado] ?? "exception", diagnostics: texto }] });

  function capacidades(base) {
    return {
      resourceType: "CapabilityStatement",
      status: "active",
      kind: "instance",
      fhirVersion: "4.0.1",
      format: ["json", "ndjson"],
      software: { name: ESTACION, version: "1.1" },
      implementation: { description: `${ESTACION} (datos sintéticos, solo lectura)`, url: base },
      instantiates: ["http://hl7.org/fhir/uv/bulkdata/CapabilityStatement/bulk-data"],
      rest: [
        {
          mode: "server",
          documentation: "Solo lectura y sin autenticación: es una simulación con datos sintéticos.",
          resource: [
            {
              type: "Patient",
              interaction: [{ code: "read" }, { code: "search-type" }],
              searchParam: [
                { name: "_id", type: "token" },
                { name: "identifier", type: "token" },
                { name: "name", type: "string" },
              ],
              operation: [{ name: "everything", definition: "http://hl7.org/fhir/OperationDefinition/Patient-everything" }],
            },
            {
              type: "Group",
              interaction: [{ code: "read" }, { code: "search-type" }],
              operation: [{ name: "export", definition: "http://hl7.org/fhir/uv/bulkdata/OperationDefinition/group-export" }],
            },
          ],
        },
      ],
    };
  }

  function buscarPacientes(indice, q, base) {
    const ids = [q.get("_id"), q.get("identifier")].filter(Boolean).flatMap((v) => v.split(",").map((x) => x.split("|").pop().trim()));
    const nombre = q.get("name") ? sinAcentos(q.get("name")) : null;
    let lista = [...indice.pacientes.values()].map((f) => f.paciente);
    if (ids.length) lista = lista.filter((p) => ids.includes(p.id));
    if (nombre) lista = lista.filter((p) => sinAcentos([p.name?.[0]?.text, ...(p.name?.[0]?.given ?? []), p.name?.[0]?.family].filter(Boolean).join(" ")).includes(nombre));
    const total = lista.length;
    const inicio = Math.max(0, Number.parseInt(q.get("_offset") ?? "0", 10) || 0);
    const cuenta = q.has("_count") ? Math.max(0, Number.parseInt(q.get("_count"), 10) || 0) : total;
    const enlace = (desde) => {
      const p = new URLSearchParams(q);
      p.set("_offset", String(desde));
      return `${base}/Patient?${p}`;
    };
    const link = [{ relation: "self", url: `${base}/Patient${[...q].length ? `?${q}` : ""}` }];
    if (inicio + cuenta < total) link.push({ relation: "next", url: enlace(inicio + cuenta) });
    return {
      resourceType: "Bundle",
      type: "searchset",
      timestamp: indice.fecha,
      total,
      link,
      entry: lista.slice(inicio, inicio + cuenta).map((p) => ({ fullUrl: `${base}/Patient/${p.id}`, resource: p, search: { mode: "match" } })),
    };
  }

  // Trabajo de exportación: "<cupo>-<versión de los datos>". No guarda estado: la exportación es inmediata.
  function indiceDeTrabajo(trabajo) {
    const m = trabajo.match(/^([a-z]+)-([0-9a-f]+)$/);
    const indice = m && CUPOS.some((c) => c.id === m[1]) ? cargar(m[1]) : null;
    if (!indice || indice.version !== m[2]) throw new ErrorHttp(404, `La exportación ${trabajo} no existe o ha caducado: vuelva a lanzar $export`);
    return indice;
  }

  function atenderFhir(req, res, prefijo = "/fhir") {
    const url = new URL(req.url, "http://localhost");
    const ruta = decodeURIComponent(url.pathname).replace(/\/+$/, "");
    const base = `http://${req.headers.host ?? "localhost"}${prefijo}`;
    if (req.method !== "GET") return error(res, 405, "Servidor de solo lectura");
    try {
      if (ruta === "/metadata") return responder(res, 200, capacidades(base));

      let m = ruta.match(/^\/\$export-status\/([^/]+)$/);
      if (m) {
        const indice = indiceDeTrabajo(m[1]);
        const pedidos = (url.searchParams.get("_type") ?? "").split(",").filter(Boolean);
        return responder(
          res,
          200,
          {
            transactionTime: indice.fecha,
            request: `${base}/Group/${indice.grupoId}/$export`,
            requiresAccessToken: false,
            output: TIPOS.filter((t) => !pedidos.length || pedidos.includes(t)).map((t) => ({
              type: t,
              url: `${base}/$export-file/${m[1]}/${t}.ndjson`,
              count: indice.ndjson[t].cuenta,
            })),
            error: [],
          },
          "application/json; charset=utf-8",
        );
      }
      m = ruta.match(/^\/\$export-file\/([^/]+)\/([A-Za-z]+)\.ndjson$/);
      if (m) {
        const fichero = indiceDeTrabajo(m[1]).ndjson[m[2]];
        if (!fichero) return error(res, 404, `La exportación no incluye el tipo ${m[2]}`);
        return responder(res, 200, fichero.datos, "application/fhir+ndjson; charset=utf-8");
      }

      const indice = cargarActivo();
      if (ruta === "/Patient") return responder(res, 200, buscarPacientes(indice, url.searchParams, base));
      m = ruta.match(/^\/Patient\/([^/]+)(\/\$everything)?$/);
      if (m) {
        const ficha = indice.pacientes.get(m[1]);
        if (!ficha) return error(res, 404, `Paciente ${m[1]} no encontrado en el ${indice.cupo.nombre.toLowerCase()}`);
        return responder(res, 200, m[2] ? fs.readFileSync(ficha.fichero, "utf-8") : ficha.paciente);
      }
      if (ruta === "/Group") {
        return responder(res, 200, {
          resourceType: "Bundle",
          type: "searchset",
          timestamp: indice.fecha,
          total: 1,
          entry: [{ fullUrl: `${base}/Group/${indice.grupoId}`, resource: grupo(indice, false), search: { mode: "match" } }],
        });
      }
      m = ruta.match(/^\/Group\/([^/]+)(\/\$export)?$/);
      if (m) {
        if (m[1] !== indice.grupoId) return error(res, 404, `El grupo ${m[1]} no existe: el cupo activo es ${indice.grupoId}`);
        if (!m[2]) return responder(res, 200, grupo(indice, true));
        const formato = url.searchParams.get("_outputFormat");
        if (formato && !/ndjson/.test(formato)) return error(res, 400, `Formato de salida no soportado: ${formato} (solo NDJSON)`);
        const tipos = url.searchParams.get("_type");
        const estado = `${base}/$export-status/${indice.cupo.id}-${indice.version}${tipos ? `?_type=${encodeURIComponent(tipos)}` : ""}`;
        return responder(res, 202, null, "application/fhir+json; charset=utf-8", { "Content-Location": estado });
      }
      return error(res, 404, `Ruta no soportada: ${ruta}`);
    } catch (e) {
      return error(res, e.estado ?? 500, e.message);
    }
  }

  function leerCuerpo(req) {
    return new Promise((resolve, reject) => {
      const trozos = [];
      req.on("data", (t) => trozos.push(t));
      req.on("end", () => {
        try {
          resolve(JSON.parse(Buffer.concat(trozos).toString("utf-8") || "{}"));
        } catch {
          reject(new ErrorHttp(400, "El cuerpo no es JSON válido"));
        }
      });
      req.on("error", reject);
    });
  }

  // Administración de la estación (no es FHIR): qué cupo está activo.
  async function atenderEstacion(req, res) {
    const ruta = new URL(req.url, "http://localhost").pathname.replace(/\/+$/, "");
    const json = (estado, cuerpo) => responder(res, estado, cuerpo, "application/json; charset=utf-8");
    try {
      if (req.method === "GET" && ruta === "/cupos") return json(200, estadoCupos());
      if (req.method === "POST" && ruta === "/cupo") {
        const { id } = await leerCuerpo(req);
        if (!CUPOS.some((c) => c.id === id)) throw new ErrorHttp(400, `Cupo desconocido: ${id}`);
        cargar(id); // deja el cupo leído (y falla aquí, sin cambiar nada, si no tiene datos)
        activo = id;
        return json(200, estadoCupos());
      }
      return json(404, { error: `Ruta no soportada: ${ruta}` });
    } catch (e) {
      return json(e.estado ?? 500, { error: e.message });
    }
  }

  return { atenderFhir, atenderEstacion, estadoCupos };
}

// Plugin de Vite: monta el servidor FHIR en /fhir y la administración en /estacion, en el puerto de la estación.
export default function servidorFhir(opciones) {
  const estacion = crearEstacion(opciones);
  const montar = (server) => {
    server.middlewares.use("/fhir", (req, res) => estacion.atenderFhir(req, res, "/fhir"));
    server.middlewares.use("/estacion", (req, res) => estacion.atenderEstacion(req, res));
  };
  return { name: "servidor-fhir-simulado", configureServer: montar, configurePreviewServer: montar };
}

// Por su cuenta (sin la interfaz de la estación): node servidor-fhir.js --port 5174
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const opcion = (nombre, defecto) => {
    const i = process.argv.indexOf(`--${nombre}`);
    return i > 0 && process.argv[i + 1] ? process.argv[i + 1] : defecto;
  };
  const puerto = Number(opcion("port", process.env.PORT ?? 5174));
  const estacion = crearEstacion({ datos: path.resolve(opcion("datos", process.env.SIMULADOR_DATOS ?? DATOS_POR_DEFECTO)), cupoInicial: opcion("cupo", process.env.SIMULADOR_CUPO ?? "demo") });
  http
    .createServer((req, res) => {
      for (const [prefijo, atender] of [["/fhir", estacion.atenderFhir], ["/estacion", estacion.atenderEstacion]]) {
        if (req.url === prefijo || req.url.startsWith(`${prefijo}/`) || req.url.startsWith(`${prefijo}?`)) {
          req.url = req.url.slice(prefijo.length) || "/";
          return atender(req, res, prefijo);
        }
      }
      res.statusCode = 404;
      return res.end("Servidor FHIR de la estación clínica simulada: use /fhir/metadata");
    })
    .listen(puerto, "127.0.0.1", () => console.log(`Servidor FHIR de la estación clínica simulada: http://localhost:${puerto}/fhir (cupo activo: ${estacion.estadoCupos().activo})`));
}
