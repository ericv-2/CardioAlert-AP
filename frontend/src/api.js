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

// `sel` = { source, cohort }: la fuente de datos y la cohorte ("demo" o "realista") elegidas en la cabecera.
export const api = {
  cohorts: (signal) => request(url("/api/cohorts"), { signal }),
  cupo: ({ source, cohort }, signal) => request(url("/api/cupo", { source, cohort }), { signal }),
  pacient: (id, { source, cohort }, signal) =>
    request(url(`/api/pacientes/${encodeURIComponent(id)}`, { source, cohort }), { signal }),
  rules: (signal) => request(url("/api/rules"), { signal }),
  saveRules: (canvis) =>
    request(url("/api/rules"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ canvis }),
    }),
  excelUrl: ({ source, cohort }) => url("/api/export/excel", { source, cohort }),
};
