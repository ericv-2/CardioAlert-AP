import { useMemo } from "react";
import { ChevronRight, CircleCheck, FlaskConical, HeartPulse, Search, TriangleAlert, Users, X } from "lucide-react";
import { NIVEL, num, pct, SEXO } from "../format.js";
import { Cargando, CategoriaCvChip, CruzadoBadge, ErrorPanel, KdigoTag, NivelChip } from "./ui.jsx";

function Kpi({ icon: Icon, tono, titulo, valor, detalle }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-line bg-white p-4 shadow-xs">
      <span className={`grid size-10 shrink-0 place-items-center rounded-lg ${tono}`}>
        <Icon className="size-5" aria-hidden="true" />
      </span>
      <div className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted">{titulo}</p>
        <p className="tabular text-3xl font-semibold leading-tight text-ink">{valor}</p>
        <p className="mt-0.5 text-xs text-muted">{detalle}</p>
      </div>
    </div>
  );
}

const sinAcentos = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

function Motivo({ p }) {
  const alertas = p.alertes_actives;
  if (alertas.length === 0) {
    return (
      <span className="flex items-start gap-1.5 text-sm text-muted">
        {p.ben_tractat && <CircleCheck className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-hidden="true" />}
        {p.resum}
      </span>
    );
  }
  const principal = alertas.reduce((a, b) => (b.pes > a.pes ? b : a));
  const accion = p.accions_recomanades[0]?.text;
  return (
    <div className="text-sm" title={p.resum}>
      <p className="line-clamp-2">
        <span className="font-semibold text-ink">{principal.titol}.</span> <span className="text-muted">{principal.motiu}</span>
      </p>
      {accion && <p className="mt-0.5 line-clamp-1 font-medium text-clinic-700">→ {accion}</p>}
      {alertas.length > 1 && <p className="mt-0.5 text-xs text-muted">+{alertas.length - 1} alertas más</p>}
    </div>
  );
}

export default function CupoView({ cupo, sel, onRetry, filtro, onFiltro, busqueda, onBusqueda }) {
  const { data, loading, error } = cupo;
  const pacientes = data?.pacients ?? [];
  const visibles = useMemo(() => {
    const q = sinAcentos(busqueda.trim());
    return pacientes.filter(
      (p) => (filtro === "TODOS" || p.nivell_risc === filtro) && (!q || sinAcentos(`${p.nom} ${p.pacient_id}`).includes(q)),
    );
  }, [pacientes, filtro, busqueda]);

  if (error) return <ErrorPanel mensaje={error} onRetry={onRetry} />;
  if (!data) return <Cargando texto={sel.source === "remote" ? "Descargando el cupo del servidor FHIR remoto…" : "Calculando el cupo…"} />;

  const k = data.kpis;
  const filtros = [
    { id: "TODOS", texto: "Todos", n: k.total },
    { id: "ALT", texto: "ALT", n: k.alt },
    { id: "MITJA", texto: "MITJA", n: k.mitja },
    { id: "BAIX", texto: "BAIX", n: k.baix },
  ];

  return (
    <div className={`space-y-5 transition-opacity ${loading ? "opacity-60" : ""}`}>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Indicadores del cupo">
        <Kpi
          icon={Users}
          tono="bg-clinic-100 text-clinic-700"
          titulo="Pacientes evaluados"
          valor={num(k.total)}
          detalle={`${k.fonts.length} sistemas de origen · ${k.dades_creuades} con datos cruzados entre comunidades`}
        />
        <Kpi
          icon={TriangleAlert}
          tono="bg-red-50 text-red-700"
          titulo="Prioridad alta (ALT)"
          valor={num(k.alt)}
          detalle={`MITJA ${k.mitja} · BAIX ${k.baix} · ${k.alertes} alertas activas`}
        />
        <Kpi
          icon={FlaskConical}
          tono="bg-amber-50 text-amber-700"
          titulo="UACR pendiente"
          valor={num(k.uacr_pendent)}
          detalle={`${k.mrc_no_diagnosticada} con criterios de ERC sin diagnóstico registrado`}
        />
        <Kpi
          icon={HeartPulse}
          tono="bg-rose-50 text-rose-700"
          titulo="Riesgo CV alto o muy alto"
          valor={num(k.risc_cv_alt)}
          detalle={`${k.risc_cv_infratractat} infratratados · ${k.ben_tractats} bien tratados (sin alerta)`}
        />
      </section>

      <section className="rounded-lg border border-line bg-white shadow-xs" aria-label="Cupo priorizado">
        <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
          <h1 className="mr-2 text-base font-semibold text-ink">Cupo priorizado</h1>
          <div className="flex rounded-md bg-clinic-50 p-0.5 ring-1 ring-line" role="group" aria-label="Filtrar por nivel de riesgo">
            {filtros.map((f) => (
              <button
                key={f.id}
                type="button"
                aria-pressed={filtro === f.id}
                onClick={() => onFiltro(f.id)}
                className={`flex items-center gap-1.5 rounded px-3 py-1.5 text-sm font-semibold transition-colors ${
                  filtro === f.id ? "bg-clinic-600 text-white shadow-sm" : "text-clinic-800 hover:bg-clinic-100"
                }`}
              >
                {NIVEL[f.id] && <span className={`size-2 rounded-full ${NIVEL[f.id].dot}`} aria-hidden="true" />}
                {f.texto}
                <span className={`tabular text-xs font-normal ${filtro === f.id ? "text-clinic-100" : "text-muted"}`}>{f.n}</span>
              </button>
            ))}
          </div>
          <div className="relative ml-auto w-full sm:w-72">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden="true" />
            <input
              type="search"
              value={busqueda}
              onChange={(e) => onBusqueda(e.target.value)}
              placeholder="Buscar por nombre o identificador"
              aria-label="Buscar paciente"
              className="h-9 w-full rounded-md border border-line bg-white pl-8 pr-8 text-sm placeholder:text-muted [&::-webkit-search-cancel-button]:hidden"
            />
            {busqueda && (
              <button
                type="button"
                onClick={() => onBusqueda("")}
                aria-label="Borrar búsqueda"
                className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-1 text-muted hover:bg-clinic-50"
              >
                <X className="size-4" aria-hidden="true" />
              </button>
            )}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[1080px] border-collapse text-left">
            <thead>
              <tr className="border-b border-line bg-clinic-50 text-[11px] font-semibold uppercase tracking-wide text-muted">
                <th scope="col" className="w-28 px-4 py-2.5">Prioridad</th>
                <th scope="col" className="px-3 py-2.5">Paciente</th>
                <th scope="col" className="px-3 py-2.5">Riñón (KDIGO)</th>
                <th scope="col" className="px-3 py-2.5">Escala aplicada</th>
                <th scope="col" className="px-3 py-2.5">Riesgo CV a 10 años</th>
                <th scope="col" className="px-3 py-2.5">Por qué y qué hacer</th>
                <th scope="col" className="w-10 px-2 py-2.5">
                  <span className="sr-only">Abrir ficha</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {visibles.map((p) => (
                <tr
                  key={p.pacient_id}
                  onClick={() => (window.location.hash = `#/paciente/${p.pacient_id}`)}
                  className="cursor-pointer border-b border-line align-top last:border-b-0 hover:bg-clinic-50"
                >
                  <td className="px-4 py-3">
                    <NivelChip nivel={p.nivell_risc} />
                    <p className="tabular mt-1 text-xs text-muted">{p.puntuacio_prioritat} puntos</p>
                  </td>
                  <td className="px-3 py-3">
                    <a
                      href={`#/paciente/${p.pacient_id}`}
                      onClick={(e) => e.stopPropagation()}
                      className="font-semibold text-clinic-700 hover:underline"
                    >
                      {p.nom}
                    </a>
                    <p className="text-xs text-muted">
                      {p.pacient_id} · {p.edat} años · {SEXO[p.sexe]}
                    </p>
                    {p.dades_creuades && (
                      <p className="mt-1">
                        <CruzadoBadge fuentes={p.fonts_dades} />
                      </p>
                    )}
                  </td>
                  <td className="px-3 py-3">
                    <KdigoTag categoria={p.categoria_kdigo} riesgo={p.risc_kdigo} />
                    <p className="tabular whitespace-nowrap text-xs text-muted">
                      FGe {num(p.fge_actual)} · UACR {p.uacr_actual == null ? "sin dato" : num(p.uacr_actual)}
                    </p>
                  </td>
                  <td className="px-3 py-3 text-sm">{p.escala_usada ?? <span className="text-muted">No calculable</span>}</td>
                  <td className="px-3 py-3">
                    <p className="tabular text-base font-semibold text-ink">{pct(p.risc_cv_percentatge)}</p>
                    <CategoriaCvChip categoria={p.categoria_risc_cv} />
                  </td>
                  <td className="max-w-md px-3 py-3">
                    <Motivo p={p} />
                  </td>
                  <td className="px-2 py-3 text-muted">
                    <ChevronRight className="size-5" aria-hidden="true" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {visibles.length === 0 && (
            <p className="px-4 py-10 text-center text-sm text-muted">Ningún paciente coincide con el filtro y la búsqueda.</p>
          )}
        </div>
        <p className="border-t border-line px-4 py-2 text-xs text-muted">
          Mostrando {visibles.length} de {k.total} pacientes, ordenados por puntuación de prioridad. Herramienta de ayuda a la decisión: no
          sustituye el juicio clínico.
        </p>
      </section>
    </div>
  );
}
