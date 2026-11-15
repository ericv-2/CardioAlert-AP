// Contexto de lanzamiento desde una estación clínica (simula un "EHR launch" de SMART on FHIR).
//
// La estación abre la interfaz del add-on con  ?iss=<servidor FHIR de la estación>&launch=<contexto>.
//   - `iss` es el servidor FHIR de la estación: de ahí se leen TODOS los datos (la ficha y el cupo). La
//     interfaz no lo consulta directamente: se lo pasa a la API del add-on en cada petición.
//   - En SMART on FHIR real, `launch` es un identificador opaco que la aplicación canjea (OAuth 2.0) por el
//     paciente y el profesional. Aquí NO hay OAuth: `launch` lleva ese mismo contexto en JSON (base64url):
//       { "patient": "P003", "intent": "ficha-paciente", "fhirUser": "Practitioner/…",
//         "practitioner": { "name", "role" }, "ehr": "…" }
//     `intent` (parámetro de contexto de SMART) dice qué pantalla abrir: "ficha-paciente" abre la ficha del
//     paciente en contexto; cualquier otro valor ("lista-trabajo"), la página principal (alertas, «Hoy» y cupo).
// Sin `launch`, la interfaz funciona como aplicación independiente y la API lee de su estación por defecto.

const INTENT_FICHA = "ficha-paciente";

function decodificar(texto) {
  const b64 = texto.replace(/-/g, "+").replace(/_/g, "/");
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  return JSON.parse(new TextDecoder().decode(bytes));
}

const consulta = new URLSearchParams(window.location.search);

// Servidor FHIR de la estación clínica (null = el que la API tenga configurado por defecto).
export const issEstacion = consulta.get("iss")?.trim() || null;

function leer() {
  const launch = consulta.get("launch");
  if (!launch) return null;
  let ctx;
  try {
    ctx = decodificar(launch);
  } catch {
    return { error: "El contexto de lanzamiento recibido de la estación clínica no es válido." };
  }
  const paciente = typeof ctx.patient === "string" && ctx.patient.trim() ? ctx.patient.trim().replace(/^Patient\//, "") : null;
  return {
    iss: issEstacion,
    paciente,
    intent: typeof ctx.intent === "string" ? ctx.intent : null,
    fhirUser: ctx.fhirUser ?? null,
    profesional: ctx.practitioner?.name ?? null,
    rol: ctx.practitioner?.role ?? null,
    estacion: ctx.ehr ?? "Estación clínica",
    embebido: window.self !== window.top,
  };
}

// Se lee una sola vez al cargar. Si la estación pide la ficha del paciente en contexto, se abre directamente;
// si no, la página principal (el paciente en contexto queda a un clic en la franja de contexto).
export const lanzamiento = leer();

if (lanzamiento?.paciente && lanzamiento.intent === INTENT_FICHA && !window.location.hash.replace(/^#\/?/, "")) {
  window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#/paciente/${encodeURIComponent(lanzamiento.paciente)}`);
}
