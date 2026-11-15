// Contexto de lanzamiento desde una estación clínica (simula un "EHR launch" de SMART on FHIR).
//
// La estación abre la interfaz del add-on con  ?iss=<servidor FHIR de la estación>&launch=<contexto>.
// En SMART on FHIR real, `launch` es un identificador opaco que la aplicación canjea (OAuth 2.0) por el
// paciente y el profesional. Aquí NO hay OAuth: `launch` lleva ese mismo contexto en JSON (base64url):
//   { "patient": "P003", "fhirUser": "Practitioner/…", "practitioner": { "name", "role" }, "ehr": "…" }
// Sin `launch`, la interfaz funciona como siempre (aplicación independiente).

function decodificar(texto) {
  const b64 = texto.replace(/-/g, "+").replace(/_/g, "/");
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  return JSON.parse(new TextDecoder().decode(bytes));
}

function leer() {
  const q = new URLSearchParams(window.location.search);
  const launch = q.get("launch");
  if (!launch) return null;
  let ctx;
  try {
    ctx = decodificar(launch);
  } catch {
    return { error: "El contexto de lanzamiento recibido de la estación clínica no es válido." };
  }
  const paciente = typeof ctx.patient === "string" && ctx.patient.trim() ? ctx.patient.trim().replace(/^Patient\//, "") : null;
  return {
    iss: q.get("iss"),
    paciente,
    fhirUser: ctx.fhirUser ?? null,
    profesional: ctx.practitioner?.name ?? null,
    rol: ctx.practitioner?.role ?? null,
    estacion: ctx.ehr ?? "Estación clínica",
    embebido: window.self !== window.top,
  };
}

// Se lee una sola vez al cargar. Con un paciente en contexto, la interfaz se abre directamente en su ficha.
export const lanzamiento = leer();

if (lanzamiento?.paciente && !window.location.hash.replace(/^#\/?/, "")) {
  window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#/paciente/${encodeURIComponent(lanzamiento.paciente)}`);
}
