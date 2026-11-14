import { useEffect, useMemo, useState } from "react";
import { Activity, ArrowRight, FlaskConical, Globe, Info, LoaderCircle, OctagonAlert, Pill, Search, Stethoscope, TriangleAlert, UserRound } from "lucide-react";
import { api } from "../api.js";
import { fecha, num, SEXO } from "../format.js";
import { Cargando, ErrorPanel } from "./ui.jsx";

// Estación clínica SIMULADA: imita de forma genérica una historia clínica de atención primaria.
// No reproduce ningún producto real. Al abrir un paciente lanza el hook patient-view de CDS Hooks
// y muestra la tarjeta que devuelve el servicio; aquí no hay lógica clínica.

const INDICADOR = {
  critical: { texto: "Crítico", icono: OctagonAlert, caja: "border-red-300 bg-red-50", barra: "bg-red-600", tono: "text-red-800" },
  warning: { texto: "Aviso", icono: TriangleAlert, caja: "border-amber-300 bg-amber-50", barra: "bg-amber-500", tono: "text-amber-900" },
  info: { texto: "Informativo", icono: Info, caja: "border-sky-200 bg-sky-50", barra: "bg-sky-600", tono: "text-sky-900" },
};

const comunidad = (origen) => (origen?.includes(" - ") ? origen.split(" - ")[1] : null);

// Markdown mínimo para el `detail` de la tarjeta: listas con "- ", **negrita** y *cursiva*.
function Inline({ texto }) {
  return texto.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g).map((t, i) => {
    if (t.startsWith("**")) return <strong key={i} className="font-semibold">{t.slice(2, -2)}</strong>;
    if (t.startsWith("*") && t.length > 2) return <em key={i} className="text-slate-600">{t.slice(1, -1)}</em>;
    return t;
  });
}

function Markdown({ texto }) {
  const bloques = [];
  for (const linea of texto.split("\n")) {
    if (linea.startsWith("- ")) {
      const ultimo = bloques.at(-1);
      if (ultimo?.lista) ultimo.lista.push(linea.slice(2));
      else bloques.push({ lista: [linea.slice(2)] });
    } else if (linea.trim()) bloques.push({ parrafo: linea });
  }
  return (
    <div className="space-y-2 text-sm text-slate-800">
      {bloques.map((b, i) =>
        b.lista ? (
          <ul key={i} className="list-disc space-y-1.5 pl-4">
            {b.lista.map((l, j) => (
              <li key={j}><Inline texto={l} /></li>
            ))}
          </ul>
        ) : (
          <p key={i}><Inline texto={b.parrafo} /></p>
        ),
      )}
    </div>
  );
}

function TarjetaCds({ card }) {
  const ind = INDICADOR[card.indicator] ?? INDICADOR.info;
  const Icono = ind.icono;
  return (
    <article className={`overflow-hidden rounded-md border ${ind.caja}`}>
      <div className={`h-1 ${ind.barra}`} />
      <div className="space-y-3 p-3">
        <div className="flex items-start gap-2">
          <Icono className={`mt-0.5 size-5 shrink-0 ${ind.tono}`} aria-hidden="true" />
          <div>
            <p className={`text-[11px] font-semibold uppercase tracking-wide ${ind.tono}`}>{ind.texto}</p>
            <h3 className="text-sm font-semibold leading-snug text-slate-900">{card.summary}</h3>
          </div>
        </div>
        {card.detail && <Markdown texto={card.detail} />}
        {card.suggestions?.length > 0 && (
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">Acciones sugeridas</p>
            <ul className="mt-1 space-y-1.5">
              {card.suggestions.map((s) => (
                <li
                  key={s.uuid}
                  className={`rounded border bg-white px-2.5 py-1.5 text-sm text-slate-800 ${s.isRecommended ? "border-teal-600" : "border-slate-200"}`}
                >
                  {s.label}
                  {s.isRecommended && <span className="ml-1.5 whitespace-nowrap text-[11px] font-semibold text-teal-700">· Recomendada</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
        <p className="text-xs text-slate-500">Fuente: {card.source?.label}</p>
      </div>
    </article>
  );
}

function PanelCds({ id, sel }) {
  const [estado, setEstado] = useState({ id: null, peticion: null, respuesta: null, error: null });

  useEffect(() => {
    const ctrl = new AbortController();
    const peticion = {
      hook: "patient-view",
      hookInstance: crypto.randomUUID(),
      context: { userId: "Practitioner/demo", patientId: id },
    };
    setEstado({ id, peticion, respuesta: null, error: null });
    api
      .cdsPatientView(peticion, sel, ctrl.signal)
      .then((respuesta) => setEstado({ id, peticion, respuesta, error: null }))
      .catch((e) => e.name !== "AbortError" && setEstado({ id, peticion, respuesta: null, error: e.message }));
    return () => ctrl.abort();
  }, [id, sel.source, sel.scale]);

  const cards = estado.id === id ? estado.respuesta?.cards : null;
  return (
    <aside className="rounded-md border border-slate-300 bg-white" aria-label="Apoyo a la decisión clínica">
      <div className="flex items-center gap-2 border-b border-slate-200 bg-slate-100 px-3 py-2">
        <Activity className="size-4 text-teal-700" aria-hidden="true" />
        <h2 className="text-sm font-semibold text-slate-900">Apoyo a la decisión</h2>
        <span className="ml-auto rounded bg-white px-1.5 py-0.5 font-mono text-[11px] text-slate-600 ring-1 ring-slate-300">CDS Hooks · patient-view</span>
      </div>
      <div className="space-y-3 p-3">
        {estado.error ? (
          <p className="text-sm text-red-800" role="alert">No se pudo consultar el servicio CDS: {estado.error}</p>
        ) : !cards ? (
          <p className="flex items-center gap-2 text-sm text-slate-600" role="status">
            <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
            Consultando el servicio CDS…
          </p>
        ) : cards.length === 0 ? (
          <p className="text-sm text-slate-600">El servicio no devuelve recomendaciones para este paciente.</p>
        ) : (
          cards.map((c) => <TarjetaCds key={c.uuid} card={c} />)
        )}
        <a href={`#/paciente/${encodeURIComponent(id)}`} className="inline-flex items-center gap-1.5 text-sm font-semibold text-teal-800 hover:underline">
          Abrir la ficha en CardioAlert AP
          <ArrowRight className="size-4" aria-hidden="true" />
        </a>
        {estado.peticion && (
          <details className="rounded border border-slate-200 text-xs">
            <summary className="cursor-pointer px-2.5 py-1.5 font-semibold text-slate-700">Ver el intercambio CDS Hooks (JSON)</summary>
            <div className="space-y-2 border-t border-slate-200 p-2.5">
              <p className="font-mono text-slate-600">POST /cds-services/cardioalert-patient-view</p>
              <pre className="max-h-40 overflow-auto rounded bg-slate-900 p-2 text-[11px] leading-relaxed text-slate-100">{JSON.stringify(estado.peticion, null, 2)}</pre>
              {estado.respuesta && (
                <pre className="max-h-64 overflow-auto rounded bg-slate-900 p-2 text-[11px] leading-relaxed text-slate-100">{JSON.stringify(estado.respuesta, null, 2)}</pre>
              )}
            </div>
          </details>
        )}
      </div>
    </aside>
  );
}

function Seccion({ titulo, icono: Icono, cuenta, children }) {
  return (
    <section className="rounded-md border border-slate-300 bg-white">
      <div className="flex items-center gap-2 border-b border-slate-200 bg-slate-100 px-3 py-2">
        <Icono className="size-4 text-teal-700" aria-hidden="true" />
        <h2 className="text-sm font-semibold text-slate-900">{titulo}</h2>
        {cuenta != null && <span className="tabular text-xs text-slate-500">({cuenta})</span>}
      </div>
      {children}
    </section>
  );
}

function Historia({ id, sel }) {
  const [estado, setEstado] = useState({ data: null, error: null });
  const [intento, setIntento] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    setEstado((s) => ({ ...s, error: null }));
    api
      .pacient(id, sel, ctrl.signal)
      .then((data) => setEstado({ data, error: null }))
      .catch((e) => e.name !== "AbortError" && setEstado({ data: null, error: e.message }));
    return () => ctrl.abort();
  }, [id, sel.source, sel.scale, intento]);

  const data = estado.data?.demografia.id === id ? estado.data : null;
  // Un "informe" = las determinaciones de una misma fecha y un mismo sistema de origen
  const informes = useMemo(() => {
    const grupos = new Map();
    for (const a of data?.analitiques ?? []) {
      const clave = `${a.data}|${a.origen ?? ""}`;
      if (!grupos.has(clave)) grupos.set(clave, { clave, fecha: a.data, origen: a.origen, filas: [] });
      grupos.get(clave).filas.push(a);
    }
    return [...grupos.values()].sort((a, b) => b.fecha.localeCompare(a.fecha));
  }, [data]);

  if (estado.error) return <ErrorPanel mensaje={estado.error} onRetry={() => setIntento((n) => n + 1)} />;
  if (!data) return <Cargando texto="Abriendo la historia clínica…" />;

  const d = data.demografia;
  const externo = (origen) => comunidad(origen) != null && data.comunitat_habitual != null && comunidad(origen) !== data.comunitat_habitual;

  return (
    <div className="space-y-3">
      <section className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-md border border-slate-300 bg-white px-4 py-3">
        <span className="grid size-11 place-items-center rounded-full bg-slate-200 text-slate-600">
          <UserRound className="size-6" aria-hidden="true" />
        </span>
        <div>
          <h1 className="text-lg font-semibold leading-tight text-slate-900">{d.nom}</h1>
          <p className="text-sm text-slate-600">Historia n.º {d.id}</p>
        </div>
        <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
          {[
            ["Edad", `${d.edat} años`],
            ["Sexo", SEXO[d.sexe] ?? d.sexe],
            ["Nacimiento", fecha(d.data_naixement)],
            ["Tabaco", d.fumador ? "Fumador" : "No fumador"],
          ].map(([k, v]) => (
            <div key={k}>
              <dt className="text-[11px] uppercase tracking-wide text-slate-500">{k}</dt>
              <dd className="font-medium text-slate-900">{v}</dd>
            </div>
          ))}
        </dl>
      </section>

      <div className="grid gap-3 md:grid-cols-2">
        <Seccion titulo="Diagnósticos" icono={Stethoscope} cuenta={data.diagnostics.length}>
          <ul className="divide-y divide-slate-200 text-sm">
            {data.diagnostics.length === 0 && <li className="px-3 py-2 text-slate-500">Sin diagnósticos registrados.</li>}
            {data.diagnostics.map((x) => (
              <li key={x.codi_ciap2} className="flex items-baseline justify-between gap-3 px-3 py-1.5">
                <span className="text-slate-900">{x.nom}</span>
                <span className="tabular whitespace-nowrap text-xs text-slate-500">
                  {x.codi_ciap2} · {x.codi_cie10} · {fecha(x.data)}
                </span>
              </li>
            ))}
          </ul>
        </Seccion>
        <Seccion titulo="Medicación activa" icono={Pill} cuenta={data.medicacions.length}>
          <ul className="divide-y divide-slate-200 text-sm">
            {data.medicacions.length === 0 && <li className="px-3 py-2 text-slate-500">Sin medicación registrada.</li>}
            {data.medicacions.map((m) => (
              <li key={m.codi_atc + m.data_inici} className="flex items-baseline justify-between gap-3 px-3 py-1.5">
                <span className="text-slate-900">{m.nom}</span>
                <span className="tabular whitespace-nowrap text-xs text-slate-500">
                  ATC {m.codi_atc} · desde {fecha(m.data_inici)}
                </span>
              </li>
            ))}
          </ul>
        </Seccion>
      </div>

      <Seccion titulo="Analíticas" icono={FlaskConical} cuenta={`${informes.length} informes`}>
        {informes.length === 0 && <p className="px-3 py-2 text-sm text-slate-500">Sin analíticas registradas.</p>}
        <div className="divide-y divide-slate-200">
          {informes.map((inf, i) => (
            <details key={inf.clave} open={i < 2 || externo(inf.origen)} className={externo(inf.origen) ? "bg-violet-50/60" : ""}>
              <summary className="flex cursor-pointer flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm">
                <span className="tabular font-semibold text-slate-900">{fecha(inf.fecha)}</span>
                <span className="text-slate-600">{inf.origen ?? "Origen no informado"}</span>
                {externo(inf.origen) && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-violet-100 px-2 py-0.5 text-xs font-semibold text-violet-900 ring-1 ring-inset ring-violet-300">
                    <Globe className="size-3" aria-hidden="true" />
                    Informe recuperado de otra comunidad
                  </span>
                )}
                <span className="ml-auto text-xs text-slate-500">
                  {inf.filas.length} {inf.filas.length === 1 ? "determinación" : "determinaciones"}
                </span>
              </summary>
              <table className="w-full border-collapse text-left text-sm">
                <tbody>
                  {inf.filas.map((a) => (
                    <tr key={a.codi_loinc} className="border-t border-slate-100">
                      <td className="py-1 pl-8 pr-3 text-slate-800">{a.nom}</td>
                      <td className="tabular w-24 px-3 py-1 text-right font-semibold text-slate-900">{num(a.valor, Number.isInteger(a.valor) ? 0 : 2)}</td>
                      <td className="w-40 px-3 py-1 text-slate-500">{a.unitat}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          ))}
        </div>
      </Seccion>
    </div>
  );
}

export default function EstacionView({ id, cupo, sel }) {
  const [busqueda, setBusqueda] = useState("");
  const pacientes = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    return [...(cupo.data?.pacients ?? [])]
      .sort((a, b) => a.pacient_id.localeCompare(b.pacient_id))
      .filter((p) => !q || p.nom.toLowerCase().includes(q) || p.pacient_id.toLowerCase().includes(q));
  }, [cupo.data, busqueda]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-md bg-slate-800 px-4 py-2.5 text-white">
        <Stethoscope className="size-5 text-teal-300" aria-hidden="true" />
        <div>
          <p className="text-base font-semibold leading-tight">Estación clínica simulada</p>
          <p className="text-xs text-slate-300">Historia clínica genérica de atención primaria · no es un producto real</p>
        </div>
        <span className="ml-auto rounded bg-amber-300 px-2.5 py-1 text-sm font-bold text-amber-950">Simulación – datos sintéticos</span>
      </div>

      <div className="grid items-start gap-3 lg:grid-cols-[15rem_minmax(0,1fr)] xl:grid-cols-[15rem_minmax(0,1fr)_23rem]">
        <nav className="rounded-md border border-slate-300 bg-white" aria-label="Pacientes del cupo">
          <div className="border-b border-slate-200 bg-slate-100 px-3 py-2">
            <h2 className="text-sm font-semibold text-slate-900">Agenda del cupo</h2>
            <label className="relative mt-2 block">
              <span className="sr-only">Buscar paciente</span>
              <Search className="pointer-events-none absolute left-2 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
              <input
                type="search"
                value={busqueda}
                onChange={(e) => setBusqueda(e.target.value)}
                placeholder="Nombre o n.º de historia"
                className="h-8 w-full rounded border border-slate-300 bg-white pl-8 pr-2 text-sm text-slate-900"
              />
            </label>
          </div>
          {cupo.error ? (
            <p className="p-3 text-sm text-red-800" role="alert">{cupo.error}</p>
          ) : !cupo.data ? (
            <p className="p-3 text-sm text-slate-500" role="status">Cargando el cupo…</p>
          ) : (
            <ul className="max-h-[70vh] overflow-auto text-sm">
              {pacientes.length === 0 && <li className="p-3 text-slate-500">Ningún paciente coincide.</li>}
              {pacientes.map((p) => (
                <li key={p.pacient_id}>
                  <a
                    href={`#/estacion/${encodeURIComponent(p.pacient_id)}`}
                    aria-current={p.pacient_id === id ? "page" : undefined}
                    className={`flex items-baseline justify-between gap-2 border-l-4 px-3 py-1.5 ${
                      p.pacient_id === id ? "border-teal-600 bg-teal-50 font-semibold text-slate-900" : "border-transparent text-slate-800 hover:bg-slate-50"
                    }`}
                  >
                    <span className="truncate">{p.nom}</span>
                    <span className="tabular whitespace-nowrap text-xs font-normal text-slate-500">
                      {p.pacient_id} · {p.edat} a
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          )}
        </nav>

        {id ? (
          <>
            <Historia id={id} sel={sel} />
            <div className="lg:col-start-2 xl:sticky xl:top-36 xl:col-start-3">
              <PanelCds id={id} sel={sel} />
            </div>
          </>
        ) : (
          <div className="rounded-md border border-dashed border-slate-300 bg-white px-6 py-16 text-center lg:col-span-1 xl:col-span-2">
            <UserRound className="mx-auto size-8 text-slate-400" aria-hidden="true" />
            <p className="mt-2 text-sm font-semibold text-slate-900">Abre un paciente de la agenda</p>
            <p className="mx-auto mt-1 max-w-md text-sm text-slate-600">
              Al abrir la historia, la estación lanza el hook <span className="font-mono">patient-view</span> de CDS Hooks y muestra la tarjeta de CardioAlert AP en el
              panel lateral.
            </p>
            <a href="#/estacion/P003" className="mt-4 inline-flex items-center gap-1.5 rounded bg-teal-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-teal-800">
              Abrir a José Fernández (P003)
              <ArrowRight className="size-4" aria-hidden="true" />
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
