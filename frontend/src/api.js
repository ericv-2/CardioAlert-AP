// Cliente de la API de CardioAlert AP. Sin lógica clínica: solo pide datos y los devuelve.
const BASE = import.meta.env.VITE_API_URL ?? "";

function url(path, params = {}) {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null && v !== ""));
  return `${BASE}${path}${q.size ? `?${q}` : ""}`;
}

async function request(input, init) {
  let res;
  try {
    res = await fetch(input, init);
  } catch (e) {
    if (e.name === "AbortError") throw e;
    throw new Error("No se puede conectar con la API de CardioAlert AP. ¿Está arrancada? (start_addon, o uvicorn api.main:app --port 8000)");
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = body?.detail;
    const err = new Error(typeof detail === "string" ? detail : detail?.missatge || `Error ${res.status}`);
    err.status = res.status;
    err.errors = detail?.errors;
    throw err;
  }
  return body;
}

// El add-on no tiene datos propios: la API los lee del servidor FHIR de la estación clínica.
// `sel` = { iss }: la dirección de ese servidor, tal como la entrega la estación al abrir el add-on (el `iss`
// del lanzamiento SMART). Sin `iss`, la API usa la estación que tiene configurada por defecto.
export const api = {
  // `refresh`: vuelve a leer el cupo de la estación (exportación Bulk Data) aunque ya esté en memoria.
  cupo: ({ iss }, { refresh = false } = {}, signal) => request(url("/api/cupo", { iss, refresh: refresh ? "true" : null }), { signal }),
  pacient: (id, { iss }, signal) => request(url(`/api/pacientes/${encodeURIComponent(id)}`, { iss }), { signal }),
  // Vuelve a leer un paciente de la estación y lo recalcula (como si llegara una analítica nueva).
  recalcular: (id, { iss }) => request(url(`/api/pacientes/${encodeURIComponent(id)}/recalcular`, { iss }), { method: "POST" }),
  // Estado de las alertas («Pendiente», «Citado», «Revisado», «Pospuesto») y lista «Hoy», sin volver a enviar el cupo.
  estados: ({ iss }, signal) => request(url("/api/estados", { iss }), { signal }),
  // `profesional`: el del contexto de lanzamiento de la estación; el cambio queda en el log de auditoría.
  cambiarEstado: (id, { iss }, { estat, fins = null, profesional }) =>
    request(url(`/api/pacientes/${encodeURIComponent(id)}/estado`, { iss }), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ estat, fins, professional: profesional }),
    }),
  rules: (signal) => request(url("/api/rules"), { signal }),
  saveRules: (canvis) =>
    request(url("/api/rules"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ canvis }),
    }),
  excelUrl: ({ iss }) => url("/api/export/excel", { iss }),
  // Petición conjunta de las pruebas pendientes (UACR, creatinina): "csv" o "xlsx".
  pruebasUrl: ({ iss }, formato) => url("/api/export/pruebas-pendientes", { iss, formato }),
};
