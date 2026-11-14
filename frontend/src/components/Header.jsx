import { Calculator, Database, HeartPulse, LoaderCircle, TriangleAlert } from "lucide-react";
import { fecha } from "../format.js";

const FUENTES = [
  { value: "local", label: "Local (eCAP / DIRAYA Demo)" },
  { value: "remote", label: "Servidor FHIR remoto" },
];
const ESCALAS = [
  { value: "score2", label: "ESC automático (SCORE2 / OP / Diabetes + CKD Add-on)" },
  { value: "regicor", label: "REGICOR" },
];

function Selector({ id, label, icon: Icon, value, onChange, options }) {
  return (
    <label htmlFor={id} className="flex flex-col gap-1">
      <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-clinic-100">
        <Icon className="size-3.5" aria-hidden="true" />
        {label}
      </span>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 max-w-[26rem] rounded-md border border-white/30 bg-white px-2.5 text-sm font-medium text-ink shadow-sm"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
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

export default function Header({ route, source, onSource, scale, onScale, meta, loading, extra, nav = [] }) {
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
            <NavLink href="#/" active={route.view !== "parametros"}>
              Cupo
            </NavLink>
            {nav.map((n) => (
              <NavLink key={n.href} href={n.href} active={route.view === n.view}>
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex flex-wrap items-end gap-3">
            <Selector id="sel-fuente" label="Fuente de datos" icon={Database} value={source} onChange={onSource} options={FUENTES} />
            <Selector id="sel-escala" label="Calculadora CV" icon={Calculator} value={scale} onChange={onScale} options={ESCALAS} />
            {extra}
          </div>
        </div>
      </div>
      <div className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-x-5 gap-y-1 px-4 py-1.5 text-xs text-muted lg:px-6">
          <span className="rounded bg-clinic-100 px-1.5 py-0.5 font-semibold text-clinic-800">Datos sintéticos</span>
          {meta ? (
            <>
              <span>
                Fuente activa: <strong className="font-semibold text-ink">{meta.font_etiqueta}</strong>
              </span>
              <span>Fecha de referencia: {fecha(meta.data_referencia)}</span>
              <span>Guía: {meta.guia}</span>
              <span>FGe: {meta.equacio_fge}</span>
            </>
          ) : (
            <span>Conectando con la API…</span>
          )}
          {loading && (
            <span className="ml-auto flex items-center gap-1.5 text-clinic-700" role="status">
              <LoaderCircle className="size-3.5 animate-spin" aria-hidden="true" />
              {source === "remote" ? "Consultando el servidor FHIR remoto…" : "Calculando el cupo…"}
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
