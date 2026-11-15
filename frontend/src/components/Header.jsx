import { Database, HeartPulse, LoaderCircle, Plug, TriangleAlert, Users } from "lucide-react";
import { fecha, num } from "../format.js";

const FUENTES = [
  { value: "local", label: "Local (eCAP / DIRAYA Demo)" },
  { value: "remote", label: "Servidor FHIR remoto" },
];

const COHORTES = [
  { id: "demo", nom: "Demo", pacients: 100, disponible: true },
  { id: "realista", nom: "Cupo realista", pacients: 1500, disponible: true },
];

function Selector({ id, label, icon: Icon, value, onChange, options, disabled = false, title }) {
  return (
    <label htmlFor={id} className="flex flex-col gap-1">
      <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-clinic-100">
        <Icon className="size-3.5" aria-hidden="true" />
        {label}
      </span>
      <select
        id={id}
        value={value}
        disabled={disabled}
        title={title}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 max-w-[26rem] rounded-md border border-white/30 bg-white px-2.5 text-sm font-medium text-ink shadow-sm disabled:cursor-not-allowed disabled:bg-clinic-100 disabled:text-muted"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value} disabled={o.disabled}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

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

export default function Header({ route, source, onSource, cohort, onCohort, cohorts, meta, loading, extra, nav = [], lanzamiento = null }) {
  const opcionesCohorte = (cohorts ?? COHORTES).map((c) => ({
    value: c.id,
    label: c.disponible ? `${c.nom} (${num(c.pacients)})` : `${c.nom} (no generada)`,
    disabled: !c.disponible,
  }));
  const soloLocal = cohort === "realista";
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
            <Selector id="sel-cohorte" label="Cohorte" icon={Users} value={cohort} onChange={onCohort} options={opcionesCohorte} />
            <Selector
              id="sel-fuente"
              label="Fuente de datos"
              icon={Database}
              value={soloLocal ? "local" : source}
              onChange={onSource}
              options={FUENTES}
              disabled={soloLocal}
              title={soloLocal ? "El cupo realista solo está disponible en local: no se sube al servidor FHIR público" : undefined}
            />
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
              <span>
                Cohorte: <strong className="font-semibold text-ink">{meta.cohort_etiqueta}</strong>
              </span>
              <span>
                Fuente activa: <strong className="font-semibold text-ink">{meta.font_etiqueta}</strong>
              </span>
              <span>Fecha de referencia: {fecha(meta.data_referencia)}</span>
              <span>
                Riesgo CV: tabla 5 de la guía {meta.guia_risc_cv} (SCORE2 / SCORE2-OP / SCORE2-Diabetes, país de riesgo bajo)
              </span>
              <span>Guía renal: {meta.guia}</span>
              <span>FGe: {meta.equacio_fge}</span>
            </>
          ) : (
            <span>Conectando con la API…</span>
          )}
          {loading && (
            <span className="ml-auto flex items-center gap-1.5 text-clinic-700" role="status">
              <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />
              {source === "remote" && !soloLocal ? "Consultando el servidor FHIR remoto…" : "Calculando el cupo…"}
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
