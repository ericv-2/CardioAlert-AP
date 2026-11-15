import { useEffect, useMemo, useState } from "react";
import { CalendarCheck, ChevronRight, CircleCheck, FlaskConical, HeartPulse, Search, Siren, Users, X } from "lucide-react";
import { ALERTA_CORTA, ESTADOS, GRUPO_CORTO, lista, num, pct, SEXO } from "../format.js";
import { Cargando, CruzadoBadge, ErrorPanel, EstadoChip, GrupoTag, KdigoTag, RiesgoCvChip } from "./ui.jsx";

const POR_PAGINA = 100; // filas que se pintan de golpe (el cupo realista tiene 1.500 pacientes)

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
  const principal = alertas.find((a) => a.regla === p.alerta_principal) ?? alertas[0];
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

// Riesgo CV: categoría de la tabla 5 (ESC 2021) con el %, la escala y el rango de referencia por edad.
function RiesgoCv({ p }) {
  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <RiesgoCvChip p={p} />
        {p.risc_cv_percentatge != null && <span className="tabular text-base font-semibold text-ink">{pct(p.risc_cv_percentatge)}</span>}
      </div>
      {p.escala_usada && <p className="text-xs text-ink">{p.escala_usada}</p>}
      {p.rang_referencia_cv && <p className="text-xs text-muted">{p.rang_referencia_cv}</p>}
      {p.regicor_referencia != null && (
        <p className="tabular text-xs text-muted" title={p.nota_calibracio}>
          REGICOR (referencia): {pct(p.regicor_referencia)}
        </p>
      )}
    </div>
  );
}

function Hoy({ pacientes, fuera }) {
  return (
    <section className="rounded-lg border border-clinic-500 bg-white shadow-xs" aria-label="Pacientes prioritarios de hoy">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-line bg-clinic-50 px-4 py-2.5">
        <h2 className="flex items-center gap-2 text-base font-semibold text-ink">
          <CalendarCheck className="size-5 text-clinic-700" aria-hidden="true" />
          Hoy: {pacientes.length} pacientes prioritarios
        </h2>
        <p className="text-xs text-muted">
          Los primeros pendientes de la lista de trabajo: alertas urgentes, después riesgo muy alto y alto sin tratamiento adecuado.
          {fuera > 0 && ` ${num(fuera)} pacientes citados, revisados o pospuestos no aparecen aquí (filtro «Estado» de la lista).`}
        </p>
      </div>
      {pacientes.length === 0 && <p className="px-4 py-4 text-sm text-muted">No quedan pacientes prioritarios pendientes.</p>}
      <ol className="grid gap-x-6 sm:grid-cols-2">
        {pacientes.map((p, i) => {
          const alerta = p.alertes_actives.find((a) => a.regla === p.alerta_principal);
          return (
            <li key={p.pacient_id} className="border-b border-line last:border-b-0">
              <a href={`#/paciente/${p.pacient_id}`} className="flex items-start gap-3 px-4 py-2.5 hover:bg-clinic-50">
                <span className="tabular mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-clinic-600 text-xs font-semibold text-white">
                  {i + 1}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                    <span className="font-semibold text-clinic-700">{p.nom}</span>
                    <span className="text-xs text-muted">
                      {p.edat} años · {SEXO[p.sexe]}
                    </span>
                    <RiesgoCvChip p={p} prefijo="Riesgo CV: " />
                  </span>
                  <span className="mt-0.5 line-clamp-1 block text-sm text-ink">{alerta ? alerta.titol : p.resum}</span>
                  {p.accions_recomanades[0] && (
                    <span className="line-clamp-1 block text-sm font-medium text-clinic-700">→ {p.accions_recomanades[0].text}</span>
                  )}
                </span>
              </a>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

export default function CupoView({ cupo, onRetry, filtro, onFiltro, busqueda, onBusqueda, filtroEstado, onFiltroEstado }) {
  const { data, loading, error } = cupo;
  const pacientes = data?.pacients ?? [];
  const estados = data?.estats ?? {};
  const [limite, setLimite] = useState(POR_PAGINA);
  const visibles = useMemo(() => {
    const q = sinAcentos(busqueda.trim());
    return pacientes.filter(
      (p) =>
        (filtro === "TODOS" || String(p.grup_ordre) === filtro) &&
        (filtroEstado === "TODOS" || (estados[p.pacient_id]?.estat ?? "pendent") === filtroEstado) &&
        (!q || sinAcentos(`${p.nom} ${p.pacient_id}`).includes(q)),
    );
  }, [pacientes, estados, filtro, filtroEstado, busqueda]);
  useEffect(() => setLimite(POR_PAGINA), [filtro, filtroEstado, busqueda, data]);
  const porId = useMemo(() => new Map(pacientes.map((p, i) => [p.pacient_id, { p, n: i + 1 }])), [pacientes]);

  if (error) return <ErrorPanel mensaje={error} onRetry={onRetry} />;
  if (!data) return <Cargando texto="Leyendo el cupo de la estación clínica y calculando…" />;

  const k = data.kpis;
  const filtros = [{ id: "TODOS", texto: "Todos", n: k.total }, ...Object.keys(k.grups).map((g) => ({ id: g, texto: GRUPO_CORTO[g], n: k.grups[g] }))];
  const hoy = (data.llista_avui ?? []).map((pid) => porId.get(pid)?.p).filter(Boolean);
  const recuento = data.recompte_estats ?? {};
  const fuera = (recuento.citat ?? 0) + (recuento.revisat ?? 0) + (recuento.posposat ?? 0);
  const filtrosEstado = [{ id: "TODOS", texto: "Todos" }, ...Object.entries(ESTADOS).map(([id, e]) => ({ id, texto: e.texto, n: recuento[id] }))];
  const pintados = visibles.slice(0, limite);
  const urgentes = lista((data.meta.alertes_urgents ?? []).map((r) => ALERTA_CORTA[r] ?? r)).replace(/^./, (c) => c.toUpperCase());

  return (
    <div className={`space-y-5 transition-opacity ${loading ? "opacity-60" : ""}`}>
      <Hoy pacientes={hoy} fuera={fuera} />

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Indicadores del cupo">
        <Kpi
          icon={Users}
          tono="bg-clinic-100 text-clinic-700"
          titulo="Pacientes evaluados"
          valor={num(k.total)}
          detalle={`${k.fonts.length} sistemas de origen · ${k.dades_creuades} con datos cruzados entre comunidades`}
        />
        <Kpi
          icon={Siren}
          tono="bg-red-50 text-red-700"
          titulo="Alertas clínicas urgentes"
          valor={num(k.grups[1])}
          detalle={`${urgentes} · ${num(k.alertes)} alertas activas en total`}
        />
        <Kpi
          icon={HeartPulse}
          tono="bg-rose-50 text-rose-700"
          titulo="Riesgo CV muy alto (ESC 2021)"
          valor={num(k.categories["Muy alto"])}
          detalle={`Alto ${num(k.categories.Alto)} · Bajo-moderado ${num(k.categories["Bajo-moderado"])}${
            k.sense_categoria ? ` · sin categoría ${num(k.sense_categoria)} (< 40 años: ${num(k.menors_edat_minima)}; faltan datos: ${num(k.falten_dades)})` : ""
          }`}
        />
        <Kpi
          icon={FlaskConical}
          tono="bg-amber-50 text-amber-700"
          titulo="UACR pendiente"
          valor={num(k.uacr_pendent)}
          detalle={`${num(k.mrc_no_diagnosticada)} con criterios de ERC sin diagnóstico · ${num(k.ben_tractats)} bien tratados (sin alerta)`}
        />
      </section>

      <section className="rounded-lg border border-line bg-white shadow-xs" aria-label="Lista de trabajo">
        <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
          <h1 className="mr-2 text-base font-semibold text-ink">Lista de trabajo</h1>
          <div className="flex flex-wrap rounded-md bg-clinic-50 p-0.5 ring-1 ring-line" role="group" aria-label="Filtrar por grupo de la lista de trabajo">
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
                {f.texto}
                <span className={`tabular text-xs font-normal ${filtro === f.id ? "text-clinic-100" : "text-muted"}`}>{num(f.n)}</span>
              </button>
            ))}
          </div>
          <label className="flex items-center gap-2 text-sm text-muted">
            Estado
            <select
              value={filtroEstado}
              onChange={(e) => onFiltroEstado(e.target.value)}
              className="h-9 rounded-md border border-line bg-white px-2 text-sm text-ink"
            >
              {filtrosEstado.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.texto}
                  {f.n != null ? ` (${num(f.n)})` : ""}
                </option>
              ))}
            </select>
          </label>
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
                <th scope="col" className="w-12 px-4 py-2.5">N.º</th>
                <th scope="col" className="px-3 py-2.5">Paciente</th>
                <th scope="col" className="w-72 px-3 py-2.5">Riesgo CV a 10 años (tabla 5, ESC 2021)</th>
                <th scope="col" className="px-3 py-2.5">Riñón (KDIGO)</th>
                <th scope="col" className="px-3 py-2.5">Por qué y qué hacer</th>
                <th scope="col" className="w-10 px-2 py-2.5">
                  <span className="sr-only">Abrir ficha</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {pintados.map((p) => (
                <tr
                  key={p.pacient_id}
                  onClick={() => (window.location.hash = `#/paciente/${p.pacient_id}`)}
                  className="cursor-pointer border-b border-line align-top last:border-b-0 hover:bg-clinic-50"
                >
                  <td className="tabular px-4 py-3 text-sm text-muted">{porId.get(p.pacient_id)?.n}</td>
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
                    <p className="mt-1">
                      <GrupoTag p={p} />
                    </p>
                    {estados[p.pacient_id] && estados[p.pacient_id].estat !== "pendent" && (
                      <p className="mt-1">
                        <EstadoChip estado={estados[p.pacient_id]} />
                      </p>
                    )}
                    {p.dades_creuades && (
                      <p className="mt-1">
                        <CruzadoBadge fuentes={p.fonts_dades} />
                      </p>
                    )}
                  </td>
                  <td className="px-3 py-3">
                    <RiesgoCv p={p} />
                  </td>
                  <td className="px-3 py-3">
                    <KdigoTag categoria={p.categoria_kdigo} riesgo={p.risc_kdigo} />
                    <p className="tabular whitespace-nowrap text-xs text-muted">
                      FGe {num(p.fge_actual)} · UACR {p.uacr_actual == null ? "sin dato" : num(p.uacr_actual)}
                    </p>
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
        {visibles.length > limite && (
          <div className="border-t border-line px-4 py-3 text-center">
            <button
              type="button"
              onClick={() => setLimite((n) => n + POR_PAGINA)}
              className="rounded-md px-4 py-2 text-sm font-semibold text-clinic-700 ring-1 ring-inset ring-line hover:bg-clinic-50"
            >
              Mostrar {Math.min(POR_PAGINA, visibles.length - limite)} más
            </button>
          </div>
        )}
        <p className="border-t border-line px-4 py-2 text-xs text-muted">
          Mostrando {num(pintados.length)} de {num(visibles.length)} pacientes ({num(k.total)} en el cupo). El orden de la lista no es una
          clasificación de riesgo: primero las alertas clínicas urgentes, después el riesgo muy alto y alto sin tratamiento adecuado y, dentro
          de cada grupo, la puntuación del motor. Herramienta de ayuda a la decisión: no sustituye el juicio clínico.
        </p>
      </section>
    </div>
  );
}
