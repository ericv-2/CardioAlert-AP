import { useEffect, useMemo, useState } from "react";
import { CircleAlert, FlaskConical, FlaskRound, Globe, LoaderCircle, Pill, RotateCw, Stethoscope, UserRound } from "lucide-react";
import { cargarHistoria, comunidad } from "../historia.js";
import { fecha, num, SEXO } from "../format.js";
import { RegistrarAnalitica } from "./Formularios.jsx";

// Historia clínica del paciente: lo que la estación sabe por sí misma (su servidor FHIR), con o sin add-on.

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

export default function Historia({ id, onCambio }) {
  const [estado, setEstado] = useState({ data: null, error: null });
  const [intento, setIntento] = useState(0);
  const [registrando, setRegistrando] = useState(false);
  const [registrada, setRegistrada] = useState(null); // última analítica registrada (aviso)
  useEffect(() => setRegistrada(null), [id]);

  useEffect(() => {
    const ctrl = new AbortController();
    setEstado((s) => ({ ...s, error: null }));
    cargarHistoria(id, ctrl.signal)
      .then((data) => setEstado({ data, error: null }))
      .catch((e) => e.name !== "AbortError" && setEstado({ data: null, error: e.message }));
    return () => ctrl.abort();
  }, [id, intento]);

  const data = estado.data?.paciente.id === id ? estado.data : null;
  // Un "informe" = las determinaciones de una misma fecha y un mismo sistema de origen
  const informes = useMemo(() => {
    const grupos = new Map();
    for (const a of data?.analiticas ?? []) {
      const clave = `${a.fecha}|${a.origen ?? ""}`;
      if (!grupos.has(clave)) grupos.set(clave, { clave, fecha: a.fecha, origen: a.origen, filas: [] });
      grupos.get(clave).filas.push(a);
    }
    return [...grupos.values()].sort((a, b) => b.fecha.localeCompare(a.fecha));
  }, [data]);

  if (estado.error) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-md border border-red-200 bg-red-50 px-6 py-10 text-center" role="alert">
        <CircleAlert className="size-7 text-red-700" aria-hidden="true" />
        <p className="max-w-xl text-sm text-red-900">{estado.error}</p>
        <button
          type="button"
          onClick={() => setIntento((n) => n + 1)}
          className="inline-flex items-center gap-2 rounded bg-white px-3 py-1.5 text-sm font-semibold text-red-800 ring-1 ring-red-300 hover:bg-red-100"
        >
          <RotateCw className="size-4" aria-hidden="true" />
          Reintentar
        </button>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="flex items-center justify-center gap-2 rounded-md border border-slate-300 bg-white py-16 text-sm text-slate-600" role="status">
        <LoaderCircle className="size-5 animate-spin text-teal-700" aria-hidden="true" />
        Abriendo la historia clínica…
      </div>
    );
  }

  const p = data.paciente;
  const externo = (origen) => comunidad(origen) != null && data.comunidadHabitual != null && comunidad(origen) !== data.comunidadHabitual;

  return (
    <div className="space-y-3">
      <section className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-md border border-slate-300 bg-white px-4 py-3">
        <span className="grid size-11 place-items-center rounded-full bg-slate-200 text-slate-600">
          <UserRound className="size-6" aria-hidden="true" />
        </span>
        <div>
          <h1 className="text-lg font-semibold leading-tight text-slate-900">{p.nombre}</h1>
          <p className="text-sm text-slate-600">Historia n.º {p.id}</p>
        </div>
        <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
          {[
            ["Edad", `${p.edad} años`],
            ["Sexo", SEXO[p.sexo] ?? p.sexo],
            ["Nacimiento", fecha(p.nacimiento)],
            ["Tabaco", p.fumador ? "Fumador" : "No fumador"],
          ].map(([k, v]) => (
            <div key={k}>
              <dt className="text-[11px] uppercase tracking-wide text-slate-500">{k}</dt>
              <dd className="font-medium text-slate-900">{v}</dd>
            </div>
          ))}
        </dl>
        <button
          type="button"
          onClick={() => setRegistrando(true)}
          className="ml-auto inline-flex items-center gap-2 rounded bg-teal-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-teal-800"
        >
          <FlaskRound className="size-4" aria-hidden="true" />
          Registrar analítica
        </button>
      </section>
      {registrada && (
        <p className="rounded border border-teal-200 bg-teal-50 px-3 py-2 text-sm text-teal-900" role="status">
          Analítica registrada: {registrada.code.text} {num(registrada.valueQuantity.value)} {registrada.valueQuantity.unit} ({registrada.performer?.[0]?.display},{" "}
          {fecha(registrada.effectiveDateTime)}). Si hay un add-on instalado, la estación se lo notifica (FHIR Subscription).
        </p>
      )}
      {registrando && (
        <RegistrarAnalitica
          paciente={p}
          hoy={data.hoy}
          origenHabitual={data.origenHabitual}
          onCerrar={() => setRegistrando(false)}
          onRegistrada={(obs) => {
            setRegistrando(false);
            setRegistrada(obs);
            setIntento((n) => n + 1);
            onCambio?.();
          }}
        />
      )}

      <div className="grid gap-3 md:grid-cols-2">
        <Seccion titulo="Diagnósticos" icono={Stethoscope} cuenta={data.diagnosticos.length}>
          <ul className="divide-y divide-slate-200 text-sm">
            {data.diagnosticos.length === 0 && <li className="px-3 py-2 text-slate-500">Sin diagnósticos registrados.</li>}
            {data.diagnosticos.map((x) => (
              <li key={x.ciap2 + x.fecha} className="flex items-baseline justify-between gap-3 px-3 py-1.5">
                <span className="text-slate-900">{x.nombre}</span>
                <span className="tabular whitespace-nowrap text-xs text-slate-500">
                  {x.ciap2} · {x.cie10} · {fecha(x.fecha)}
                </span>
              </li>
            ))}
          </ul>
        </Seccion>
        <Seccion titulo="Medicación activa" icono={Pill} cuenta={data.medicacion.length}>
          <ul className="divide-y divide-slate-200 text-sm">
            {data.medicacion.length === 0 && <li className="px-3 py-2 text-slate-500">Sin medicación registrada.</li>}
            {data.medicacion.map((m) => (
              <li key={m.atc + m.inicio} className="flex items-baseline justify-between gap-3 px-3 py-1.5">
                <span className="text-slate-900">{m.nombre}</span>
                <span className="tabular whitespace-nowrap text-xs text-slate-500">
                  ATC {m.atc} · desde {fecha(m.inicio)}
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
                    <tr key={a.loinc} className="border-t border-slate-100">
                      <td className="py-1 pl-8 pr-3 text-slate-800">{a.nombre}</td>
                      <td className="tabular w-24 px-3 py-1 text-right font-semibold text-slate-900">{num(a.valor, Number.isInteger(a.valor) ? 0 : 2)}</td>
                      <td className="w-40 px-3 py-1 text-slate-500">{a.unidad}</td>
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
