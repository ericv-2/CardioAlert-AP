// Integración de la estación con un add-on de apoyo a la decisión, solo por estándares:
//   - HL7 CDS Hooks: discovery (GET {url}/cds-services) al instalar y hook patient-view al abrir un paciente.
//     La petición lleva `fhirServer` (el servidor FHIR de la estación): el add-on lee de ahí los datos.
//   - Lanzamiento de la interfaz del add-on con el paciente y el profesional como contexto
//     (simula un "EHR launch" de SMART on FHIR, sin OAuth).
// La estación no sabe nada del add-on más allá de su URL: todo lo demás lo aprende del discovery.
import { fhirBase } from "./historia.js";

export const URL_POR_DEFECTO = "http://localhost:8000";
const CLAVE = "estacion-simulada.integracion.v1"; // estado de instalación guardado en el navegador
const HOOK = "patient-view";
const EXTENSION_APP = "cardioalert-app"; // extensión del discovery con la interfaz embebible del add-on

// Profesional que tiene la sesión abierta en la estación (simulado).
export const PROFESIONAL = { id: "Practitioner/sim-0001", nombre: "Dra. Carmen Soler", rol: "Medicina de familia" };
export const ESTACION = "Estación clínica simulada";

export function leerInstalacion() {
  try {
    const v = JSON.parse(window.localStorage.getItem(CLAVE));
    return v && typeof v.url === "string" && Array.isArray(v.servicios) ? v : null;
  } catch {
    return null;
  }
}

function guardarInstalacion(instalacion) {
  try {
    if (instalacion) window.localStorage.setItem(CLAVE, JSON.stringify(instalacion));
    else window.localStorage.removeItem(CLAVE);
  } catch {
    // sin almacenamiento (modo privado): la instalación dura hasta recargar
  }
}

export function normalizarUrl(texto) {
  let url = texto.trim().replace(/\/+$/, "");
  if (!url) throw new Error("Escriba la URL del add-on (por ejemplo, http://localhost:8000).");
  if (!/^https?:\/\//i.test(url)) url = `http://${url}`;
  try {
    new URL(url);
  } catch {
    throw new Error(`«${texto.trim()}» no es una URL válida.`);
  }
  return url.replace(/\/cds-services$/, "");
}

// fetch con límite de tiempo: si el add-on no contesta, la estación no se queda esperando.
async function pedir(url, opciones = {}, { segundos = 8, signal } = {}) {
  const ctrl = new AbortController();
  let agotado = false;
  const reloj = setTimeout(() => {
    agotado = true;
    ctrl.abort();
  }, segundos * 1000);
  const abortar = () => ctrl.abort();
  signal?.addEventListener("abort", abortar);
  try {
    return await fetch(url, { ...opciones, signal: ctrl.signal });
  } catch (e) {
    if (e.name === "AbortError" && !agotado) throw e; // cancelada por la propia estación (cambio de paciente)
    const err = new Error(agotado ? `no ha respondido en ${segundos} segundos` : "no se puede conectar");
    err.sinRespuesta = true;
    throw err;
  } finally {
    clearTimeout(reloj);
    signal?.removeEventListener("abort", abortar);
  }
}

// Discovery de CDS Hooks. Devuelve los servicios y, si el add-on la anuncia, su interfaz embebible.
export async function descubrir(url, signal) {
  const destino = `${url}/cds-services`;
  let res;
  try {
    res = await pedir(destino, { headers: { Accept: "application/json" } }, { segundos: 6, signal });
  } catch (e) {
    if (e.name === "AbortError") throw e;
    const err = new Error(`El add-on no responde en ${destino} (${e.message}). Compruebe la URL y que el add-on está arrancado.`);
    err.sinRespuesta = true;
    throw err;
  }
  const cuerpo = await res.json().catch(() => null);
  if (!res.ok) throw new Error(`${destino} ha respondido con un error ${res.status}.`);
  const servicios = Array.isArray(cuerpo?.services) ? cuerpo.services.filter((s) => s?.id && s?.hook) : null;
  if (!servicios) throw new Error(`${destino} no es un servicio CDS Hooks: la respuesta no tiene la lista «services».`);
  if (servicios.length === 0) throw new Error(`${destino} responde, pero no ofrece ningún servicio.`);
  const conApp = servicios.find((s) => s.extension?.[EXTENSION_APP]?.launchUrl);
  const ext = conApp?.extension[EXTENSION_APP];
  return {
    servicios,
    app: ext ? { titulo: ext.title || conApp.title || "Add-on", launchUrl: String(ext.launchUrl).replace(/\/+$/, ""), descripcion: ext.description ?? null } : null,
    respuesta: cuerpo,
  };
}

// --- FHIR Subscription (R4 Backport IG): avisar al add-on cuando entra una analítica de un paciente del cupo ---
// El add-on anuncia en el discovery qué suscripción quiere (tema y endpoint); la estación la registra en su
// propio servidor FHIR al instalarlo y la borra al desinstalarlo.
const suscripcionPedida = (respuesta) =>
  respuesta?.services?.map((s) => s.extension?.[EXTENSION_APP]?.subscription).find((s) => s?.topic && s?.endpoint) ?? null;

async function crearSuscripcion(url, pedida) {
  const endpoint = new URL(pedida.endpoint, `${url}/`).href;
  const res = await fetch(`${fhirBase()}/Subscription`, {
    method: "POST",
    headers: { "Content-Type": "application/fhir+json", Accept: "application/fhir+json" },
    body: JSON.stringify({
      resourceType: "Subscription",
      status: "requested",
      reason: `${pedida.description ?? "Notificaciones"} (add-on ${url})`,
      criteria: pedida.topic,
      channel: { type: "rest-hook", endpoint, payload: pedida.payload ?? "application/fhir+json" },
    }),
  });
  const cuerpo = await res.json().catch(() => null);
  if (!res.ok) throw new Error(cuerpo?.issue?.[0]?.diagnostics || `la estación no ha podido registrar la suscripción (${res.status})`);
  return { id: cuerpo.id, endpoint, tema: pedida.topic };
}

export async function instalar(textoUrl) {
  const url = normalizarUrl(textoUrl);
  const { servicios, app, respuesta } = await descubrir(url);
  const pedida = suscripcionPedida(respuesta);
  const suscripcion = pedida ? await crearSuscripcion(url, pedida) : null;
  const instalacion = { url, servicios, app, discovery: respuesta, suscripcion, instaladoEn: new Date().toISOString() };
  guardarInstalacion(instalacion);
  return instalacion;
}

// La suscripción vive en la memoria del servidor de la estación: si se ha reiniciado, se vuelve a registrar.
export async function asegurarSuscripcion(instalacion) {
  const pedida = suscripcionPedida(instalacion?.discovery);
  if (!pedida) return instalacion;
  if (instalacion.suscripcion?.id) {
    const res = await fetch(`${fhirBase()}/Subscription/${encodeURIComponent(instalacion.suscripcion.id)}`, { headers: { Accept: "application/fhir+json" } });
    if (res.ok) return instalacion;
  }
  const nueva = { ...instalacion, suscripcion: await crearSuscripcion(instalacion.url, pedida) };
  guardarInstalacion(nueva);
  return nueva;
}

export async function desinstalar(instalacion) {
  guardarInstalacion(null);
  if (instalacion?.suscripcion?.id) {
    await fetch(`${fhirBase()}/Subscription/${encodeURIComponent(instalacion.suscripcion.id)}`, { method: "DELETE" }).catch(() => {});
  }
}

export const servicioPatientView = (instalacion) => instalacion?.servicios.find((s) => s.hook === HOOK) ?? null;
export const nombreAddon = (instalacion) => instalacion?.app?.titulo || servicioPatientView(instalacion)?.title || "Add-on";

// Hook patient-view: se lanza al abrir la historia de un paciente. Devuelve { peticion, url, respuesta }.
export function peticionPatientView(pacienteId) {
  return {
    hook: HOOK,
    hookInstance: crypto.randomUUID(),
    fhirServer: fhirBase(),
    context: { userId: PROFESIONAL.id, patientId: pacienteId },
  };
}

export async function llamarPatientView(instalacion, peticion, signal) {
  const servicio = servicioPatientView(instalacion);
  const destino = `${instalacion.url}/cds-services/${encodeURIComponent(servicio.id)}`;
  let res;
  try {
    res = await pedir(
      destino,
      { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(peticion) },
      { segundos: 10, signal },
    );
  } catch (e) {
    if (e.name === "AbortError") throw e;
    const err = new Error(`El add-on no responde en ${instalacion.url} (${e.message}).`);
    err.sinRespuesta = true;
    throw err;
  }
  const cuerpo = await res.json().catch(() => null);
  if (!res.ok) {
    const detalle = typeof cuerpo?.detail === "string" ? cuerpo.detail : `error ${res.status}`;
    throw new Error(`El servicio CDS ha rechazado la petición: ${detalle}.`);
  }
  return cuerpo;
}

// --- Lanzamiento de la interfaz del add-on (SMART on FHIR simulado) ---

function base64url(texto) {
  const bytes = new TextEncoder().encode(texto);
  let binario = "";
  for (const b of bytes) binario += String.fromCharCode(b);
  return btoa(binario).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

// Contexto que la estación entrega al add-on. En SMART on FHIR real llegaría en la respuesta del token.
// `intent` (parámetro de contexto de SMART) dice qué pantalla del add-on se quiere abrir: la página principal
// ("lista-trabajo": alertas, «Hoy» y cupo) o la ficha del paciente en contexto ("ficha-paciente").
export const INTENT = { cupo: "lista-trabajo", ficha: "ficha-paciente" };

export function contextoLanzamiento(pacienteId, vista = "cupo") {
  return {
    patient: pacienteId ?? null,
    intent: pacienteId && vista === "ficha" ? INTENT.ficha : INTENT.cupo,
    fhirUser: PROFESIONAL.id,
    practitioner: { name: PROFESIONAL.nombre, role: PROFESIONAL.rol },
    ehr: ESTACION,
    simulated: true,
  };
}

// `iss` es la dirección del servidor FHIR de la estación: de ahí lee el add-on los datos de los pacientes.
export function urlLanzamiento(instalacion, pacienteId, vista = "cupo") {
  const q = new URLSearchParams({ iss: fhirBase(), launch: base64url(JSON.stringify(contextoLanzamiento(pacienteId, vista))) });
  return `${instalacion.app.launchUrl}/?${q}`;
}

// ¿Responde la interfaz del add-on? Es otro origen: basta con saber si hay alguien escuchando.
export async function interfazResponde(instalacion) {
  try {
    await pedir(instalacion.app.launchUrl, { mode: "no-cors", cache: "no-store" }, { segundos: 5 });
    return true;
  } catch {
    return false;
  }
}
