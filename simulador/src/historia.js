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

// Agenda: los pacientes del cupo. `fecha` es el "hoy" de la simulación (fecha de extracción de los datos).
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

  return { paciente: { ...paciente(de("Patient")[0], hoy), fumador }, analiticas, diagnosticos, medicacion, comunidadHabitual };
}

export const comunidad = (origen) => (origen?.includes(" - ") ? origen.split(" - ").slice(1).join(" - ") : null);
