// Historia clínica de la estación: lee su propio servidor FHIR (/fhir) y lo pasa a un modelo sencillo
// para pintar. No hay lógica clínica ni dependencia del add-on.
const FHIR = "/fhir";
const LOINC = "http://loinc.org";
const CIAP2 = "http://hl7.org/fhir/sid/icpc-2";
const CIE10 = "http://hl7.org/fhir/sid/icd-10";
const ATC = "http://www.whocc.no/atc";
const SNOMED = "http://snomed.info/sct";
const LOINC_TABACO = "72166-2";
const SNOMED_FUMADORES = new Set(["449868002", "77176002", "428041000124106", "428071000124103", "428061000124105"]);

// Dirección del servidor FHIR de la estación tal como la ve otra aplicación (el `iss` / `fhirServer`).
export const fhirBase = () => `${window.location.origin}${FHIR}`;

async function pedir(ruta, signal) {
  let res;
  try {
    res = await fetch(`${FHIR}${ruta}`, { signal, headers: { Accept: "application/fhir+json" } });
  } catch (e) {
    if (e.name === "AbortError") throw e;
    throw new Error("No se puede leer la historia clínica de la estación (¿está arrancado el simulador?).");
  }
  const cuerpo = await res.json().catch(() => null);
  if (!res.ok) throw new Error(cuerpo?.issue?.[0]?.diagnostics || `Error ${res.status} del servidor FHIR de la estación`);
  return cuerpo;
}

const codigo = (concepto, sistema) => concepto?.coding?.find((c) => c.system === sistema)?.code ?? "";
const dia = (texto) => texto?.slice(0, 10) ?? null;

function edadEn(nacimiento, referencia) {
  const [y, m, d] = nacimiento.split("-").map(Number);
  const [ry, rm, rd] = referencia.split("-").map(Number);
  return ry - y - (rm < m || (rm === m && rd < d) ? 1 : 0);
}

function paciente(p, referencia) {
  const nombre = p.name?.[0] ?? {};
  const nacimiento = dia(p.birthDate);
  return {
    id: p.id,
    nombre: nombre.text || [...(nombre.given ?? []), nombre.family ?? ""].join(" ").trim(),
    sexo: p.gender === "male" ? "H" : "D",
    nacimiento,
    edad: nacimiento && referencia ? edadEn(nacimiento, referencia) : null,
  };
}

// Cupos de la estación y cuál está activo (administración de la estación, no es FHIR).
async function pedirEstacion(ruta, opciones) {
  let res;
  try {
    res = await fetch(`/estacion${ruta}`, opciones);
  } catch (e) {
    if (e.name === "AbortError") throw e;
    throw new Error("La estación no responde (¿está arrancado el simulador?).");
  }
  const cuerpo = await res.json().catch(() => null);
  if (!res.ok) throw new Error(cuerpo?.error || `Error ${res.status} de la estación`);
  return cuerpo;
}

export const cargarCupos = (signal) => pedirEstacion("/cupos", { signal });

// Cambia el cupo activo: a partir de aquí el servidor FHIR de la estación sirve los pacientes de ese cupo.
export const activarCupo = (id) =>
  pedirEstacion("/cupo", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id }) });

// Agenda: los pacientes del cupo activo. `fecha` es el "hoy" de la simulación (fecha de extracción de los datos).
export async function cargarAgenda(signal) {
  const bundle = await pedir("/Patient", signal);
  const hoy = dia(bundle.timestamp) ?? new Date().toISOString().slice(0, 10);
  const pacientes = (bundle.entry ?? []).map((e) => paciente(e.resource, hoy)).sort((a, b) => a.id.localeCompare(b.id));
  return { fecha: hoy, pacientes };
}

// Historia completa de un paciente: datos, diagnósticos, medicación y analíticas con su sistema de origen.
export async function cargarHistoria(id, signal) {
  const bundle = await pedir(`/Patient/${encodeURIComponent(id)}/$everything`, signal);
  const hoy = dia(bundle.timestamp) ?? new Date().toISOString().slice(0, 10);
  const recursos = (bundle.entry ?? []).map((e) => e.resource);
  const de = (tipo) => recursos.filter((r) => r.resourceType === tipo);

  let fumador = false;
  const analiticas = [];
  for (const o of de("Observation")) {
    const loinc = codigo(o.code, LOINC);
    if (loinc === LOINC_TABACO) fumador = SNOMED_FUMADORES.has(codigo(o.valueCodeableConcept, SNOMED));
    else if (o.valueQuantity) {
      analiticas.push({
        loinc,
        nombre: o.code.text || o.code.coding?.[0]?.display || "",
        valor: Number(o.valueQuantity.value),
        unidad: o.valueQuantity.unit ?? "",
        fecha: dia(o.effectiveDateTime),
        origen: o.performer?.find((x) => x.display)?.display ?? null,
      });
    }
  }
  analiticas.sort((a, b) => a.fecha.localeCompare(b.fecha) || a.loinc.localeCompare(b.loinc));

  const diagnosticos = de("Condition")
    .map((c) => ({ ciap2: codigo(c.code, CIAP2), cie10: codigo(c.code, CIE10), nombre: c.code?.text ?? "", fecha: dia(c.onsetDateTime || c.recordedDate) }))
    .sort((a, b) => a.fecha.localeCompare(b.fecha) || a.ciap2.localeCompare(b.ciap2));

  const medicacion = de("MedicationStatement")
    .map((m) => ({
      nombre: m.medicationCodeableConcept?.text ?? "",
      atc: codigo(m.medicationCodeableConcept, ATC),
      inicio: dia(m.effectivePeriod?.start || m.effectiveDateTime),
    }))
    .sort((a, b) => a.inicio.localeCompare(b.inicio) || a.atc.localeCompare(b.atc));

  // Comunidad habitual: la de la mayoría de sus analíticas (orígenes con formato "Sistema - Comunidad").
  // Un informe de otra comunidad se marca como recuperado de fuera.
  const cuenta = new Map();
  for (const a of analiticas) {
    const c = comunidad(a.origen);
    if (c) cuenta.set(c, (cuenta.get(c) ?? 0) + 1);
  }
  const comunidadHabitual = [...cuenta.entries()].reduce((mejor, e) => (!mejor || e[1] > mejor[1] ? e : mejor), null)?.[0] ?? null;

  const origenHabitual = analiticas.find((a) => comunidad(a.origen) === comunidadHabitual)?.origen ?? null;
  return { paciente: { ...paciente(de("Patient")[0], hoy), fumador }, analiticas, diagnosticos, medicacion, comunidadHabitual, origenHabitual, hoy };
}

// --- Escritura en la historia (servidor FHIR de la estación) ---

// Pruebas que se pueden registrar a mano (LOINC, unidad UCUM). La fecha la pone la estación: "hoy".
export const PRUEBAS = [
  { loinc: "9318-7", nombre: "Cociente albúmina/creatinina en orina", unidad: "mg/g", ucum: "mg/g", categoria: "laboratory" },
  { loinc: "2160-0", nombre: "Creatinina", unidad: "mg/dL", ucum: "mg/dL", categoria: "laboratory" },
  { loinc: "4548-4", nombre: "Hemoglobina glicada (HbA1c)", unidad: "%", ucum: "%", categoria: "laboratory" },
  { loinc: "33762-6", nombre: "NT-proBNP", unidad: "pg/mL", ucum: "pg/mL", categoria: "laboratory" },
  { loinc: "13457-7", nombre: "Colesterol LDL", unidad: "mg/dL", ucum: "mg/dL", categoria: "laboratory" },
  { loinc: "2093-3", nombre: "Colesterol total", unidad: "mg/dL", ucum: "mg/dL", categoria: "laboratory" },
  { loinc: "2085-9", nombre: "Colesterol HDL", unidad: "mg/dL", ucum: "mg/dL", categoria: "laboratory" },
  { loinc: "2823-3", nombre: "Potasio", unidad: "mmol/L", ucum: "mmol/L", categoria: "laboratory" },
  { loinc: "8480-6", nombre: "Presión arterial sistólica", unidad: "mmHg", ucum: "mm[Hg]", categoria: "vital-signs" },
  { loinc: "8462-4", nombre: "Presión arterial diastólica", unidad: "mmHg", ucum: "mm[Hg]", categoria: "vital-signs" },
];
export const ORIGENES = ["eCAP - Catalunya", "DIRAYA - Andalucía", "SERGAS - Galicia", "Lab. Hospital"];

async function escribir(ruta, recurso) {
  let res;
  try {
    res = await fetch(`${FHIR}${ruta}`, {
      method: "POST",
      headers: { "Content-Type": "application/fhir+json", Accept: "application/fhir+json" },
      body: JSON.stringify(recurso),
    });
  } catch {
    throw new Error("La estación no responde (¿está arrancado el simulador?).");
  }
  const cuerpo = await res.json().catch(() => null);
  if (!res.ok) throw new Error(cuerpo?.issue?.[0]?.diagnostics || `Error ${res.status} del servidor FHIR de la estación`);
  return cuerpo;
}

export function registrarAnalitica(pacienteId, { prueba, valor, origen }) {
  return escribir("/Observation", {
    resourceType: "Observation",
    status: "final",
    category: [{ coding: [{ system: "http://terminology.hl7.org/CodeSystem/observation-category", code: prueba.categoria }] }],
    code: { coding: [{ system: LOINC, code: prueba.loinc, display: prueba.nombre }], text: prueba.nombre },
    subject: { reference: `Patient/${pacienteId}` },
    valueQuantity: { value: Number(valor), unit: prueba.unidad, system: "http://unitsofmeasure.org", code: prueba.ucum },
    performer: [{ display: origen }],
  });
}

export function altaPaciente({ nombre, apellidos, sexo, nacimiento }) {
  return escribir("/Patient", {
    resourceType: "Patient",
    name: [{ use: "official", given: nombre.trim().split(/\s+/), family: apellidos.trim() }],
    gender: sexo === "H" ? "male" : "female",
    birthDate: nacimiento,
  });
}

export const comunidad = (origen) => (origen?.includes(" - ") ? origen.split(" - ").slice(1).join(" - ") : null);
