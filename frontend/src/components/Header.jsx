import { Database, HeartPulse, LoaderCircle, Plug, RotateCw, TriangleAlert } from "lucide-react";
import { fecha } from "../format.js";

function NavLink({ href, active, children }) {
  return (
    <a
      href={href}
      aria-current={active ? "page" : undefined}
      className={`rounded-md px-3 py-1.5 text-sm font-semibold transition-colors ${
        active ? "bg-white text-clinic-700" : "text-white hover:bg-white/15"
      }`}
    >
      {children}
    </a>
  );
}

// Franja de contexto cuando la interfaz se abre desde una estación clínica (lanzamiento SMART on FHIR simulado).
function Contexto({ lanzamiento, route }) {
  if (lanzamiento.error) {
    return (
      <div className="border-b border-amber-300 bg-amber-50" role="alert">
        <div className="mx-auto flex max-w-[1440px] items-start gap-2 px-4 py-2 text-sm text-amber-900 lg:px-6">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>{lanzamiento.error} Se muestra el cupo completo.</span>
        </div>
      </div>
    );
  }
  const enFicha = route.view === "paciente" && route.id === lanzamiento.paciente;
  return (
    <div className="border-b border-clinic-200 bg-clinic-100" aria-label="Contexto recibido de la estación clínica">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-x-5 gap-y-1 px-4 py-1.5 text-sm text-clinic-900 lg:px-6">
        <span className="flex items-center gap-1.5 font-semibold">
          <Plug className="size-4" aria-hidden="true" />
          Abierto desde: {lanzamiento.estacion}
        </span>
        {lanzamiento.profesional && (
          <span>
            Profesional: <strong className="font-semibold">{lanzamiento.profesional}</strong>
            {lanzamiento.rol && <span className="text-clinic-800"> · {lanzamiento.rol}</span>}
          </span>
        )}
        <span>
          Paciente en contexto: <strong className="font-semibold">{lanzamiento.paciente ?? "ninguno"}</strong>
        </span>
        <span className="rounded bg-white px-1.5 py-0.5 text-xs text-clinic-800 ring-1 ring-clinic-200">Lanzamiento SMART on FHIR simulado</span>
        <span className="ml-auto flex items-center gap-1">
          {lanzamiento.paciente && (
            <a
              href={`#/paciente/${encodeURIComponent(lanzamiento.paciente)}`}
              aria-current={enFicha ? "page" : undefined}
              className={`rounded px-2.5 py-1 text-sm font-semibold ${enFicha ? "bg-clinic-600 text-white" : "text-clinic-800 hover:bg-white"}`}
            >
              Ficha de {lanzamiento.paciente}
            </a>
          )}
          <a
            href="#/"
            aria-current={route.view === "cupo" ? "page" : undefined}
            className={`rounded px-2.5 py-1 text-sm font-semibold ${route.view === "cupo" ? "bg-clinic-600 text-white" : "text-clinic-800 hover:bg-white"}`}
          >
            Lista «Hoy» y cupo
          </a>
        </span>
      </div>
    </div>
  );
}

// De qué sistema se están leyendo los datos. Solo informa: el add-on no tiene datos propios ni elige el cupo;
// lee del servidor FHIR de la estación clínica, y el cupo es el que la estación tiene activo.
function DatosDe({ meta, loading, sinDatos, onReleer }) {
  const texto = meta ? meta.dades_de : sinDatos ? "Sin conexión con la estación clínica" : "Conectando con la estación clínica…";
  return (
    <div className="flex items-end gap-2">
      <div className="flex flex-col gap-1" title={meta?.fhir_server ? `Servidor FHIR: ${meta.fhir_server}` : undefined}>
        <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-clinic-100">
          <Database className="size-3.5" aria-hidden="true" />
          Datos de
        </span>
        <span className="flex h-9 max-w-[30rem] items-center rounded-md bg-white/15 px-2.5 text-sm font-semibold text-white ring-1 ring-inset ring-white/25">
          <span className="truncate">{texto}</span>
        </span>
      </div>
      <button
        type="button"
        onClick={onReleer}
        disabled={loading}
        title="Volver a leer el cupo de la estación clínica y recalcular"
        className="inline-flex h-9 items-center gap-1.5 rounded-md px-2.5 text-sm font-semibold text-white ring-1 ring-inset ring-white/40 hover:bg-white/15 disabled:cursor-not-allowed disabled:opacity-60"
      >
        <RotateCw className={`size-4 ${loading ? "animate-spin" : ""}`} aria-hidden="true" />
        Actualizar
      </button>
    </div>
  );
}

export default function Header({ route, meta, loading, sinDatos = false, onReleer, extra, nav = [], lanzamiento = null }) {
  return (
    <header className="sticky top-0 z-30 shadow-sm">
      <div className="bg-clinic-600 text-white">
        <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 lg:px-6">
          <a href="#/" className="flex items-center gap-3 rounded-md">
            <span className="grid size-10 place-items-center rounded-lg bg-white/15">
              <HeartPulse className="size-6" aria-hidden="true" />
            </span>
            <span>
              <span className="block text-lg font-semibold leading-tight">CardioAlert AP</span>
              <span className="block text-xs text-clinic-100">Cribado cardiorrenal-metabólico · Atención Primaria</span>
            </span>
          </a>
          <nav className="flex items-center gap-1" aria-label="Secciones">
            <NavLink href="#/" active={route.view === "cupo" || route.view === "paciente"}>
              Cupo
            </NavLink>
            {nav.map((n) => (
              <NavLink key={n.href} href={n.href} active={route.view === n.view}>
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex flex-wrap items-end gap-3">
            <DatosDe meta={meta} loading={loading} sinDatos={sinDatos} onReleer={onReleer} />
            {extra}
          </div>
        </div>
      </div>
      {lanzamiento && <Contexto lanzamiento={lanzamiento} route={route} />}
      <div className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-x-5 gap-y-1 px-4 py-1.5 text-xs text-muted lg:px-6">
          <span className="rounded bg-clinic-100 px-1.5 py-0.5 font-semibold text-clinic-800">Datos sintéticos</span>
          {meta ? (
            <>
              {meta.fhir_server && (
                <span>
                  Servidor FHIR: <span className="font-mono text-[11px] text-ink">{meta.fhir_server}</span>
                </span>
              )}
              <span>Fecha de referencia: {fecha(meta.data_referencia)}</span>
              <span>
                Riesgo CV: tabla 5 de la guía {meta.guia_risc_cv} (SCORE2 / SCORE2-OP / SCORE2-Diabetes, país de riesgo bajo)
              </span>
              <span>Guía renal: {meta.guia}</span>
              <span>FGe: {meta.equacio_fge}</span>
            </>
          ) : (
            <span>{sinDatos ? "Sin datos: no se ha podido leer la estación clínica" : "Leyendo los datos de la estación clínica…"}</span>
          )}
          {loading && (
            <span className="ml-auto flex items-center gap-1.5 text-clinic-700" role="status">
              <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />
              Leyendo el cupo de la estación y calculando…
            </span>
          )}
        </div>
      </div>
      {meta?.avis && (
        <div className="border-b border-amber-300 bg-amber-50" role="alert">
          <div className="mx-auto flex max-w-[1440px] items-start gap-2 px-4 py-2 text-sm text-amber-900 lg:px-6">
            <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <span>{meta.avis}</span>
          </div>
        </div>
      )}
    </header>
  );
}
