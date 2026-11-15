import { ArrowLeftRight, CircleAlert, LoaderCircle, RotateCw } from "lucide-react";
import { CATEGORIA_CV, ESTADOS, KDIGO, textoEstado } from "../format.js";

const CHIP = "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ring-inset";

// Estado de la alerta del paciente («Pendiente», «Citado», «Revisado», «Pospuesto hasta …»).
export function EstadoChip({ estado }) {
  const e = estado ?? { estat: "pendent" };
  return (
    <span className={`${CHIP} ${ESTADOS[e.estat]?.clase ?? ESTADOS.pendent.clase}`} title={e.qui ? `Último cambio: ${e.qui}` : undefined}>
      {textoEstado(e)}
    </span>
  );
}

// Nivel de riesgo CV: la categoría de la tabla 5 (ESC 2021) o, si no la hay, el motivo ("Faltan datos…").
export function RiesgoCvChip({ p, prefijo = "" }) {
  if (!p.categoria_risc_cv) {
    return <span className={`${CHIP} whitespace-normal bg-slate-100 text-slate-700 ring-slate-300`}>{p.text_risc_cv || "No calculable"}</span>;
  }
  return (
    <span className={`${CHIP} ${CATEGORIA_CV[p.categoria_risc_cv]}`} title="Categoría de riesgo de la tabla 5 de la guía ESC 2021">
      {prefijo}
      {p.categoria_risc_cv}
    </span>
  );
}

// Posición en la lista de trabajo: etiqueta neutra, sin semáforo (no es una clasificación de riesgo).
export function GrupoTag({ p }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted" title="Grupo del orden de la lista de trabajo (no es una clasificación de riesgo)">
      <span className="tabular grid size-4 place-items-center rounded-sm bg-clinic-100 text-[10px] font-semibold text-clinic-800">{p.grup_ordre}</span>
      {p.grup_ordre_text}
    </span>
  );
}

export function KdigoTag({ categoria, riesgo }) {
  if (!categoria) return <span className="text-xs text-muted">Sin creatinina</span>;
  const k = KDIGO[riesgo];
  return (
    <span className="inline-flex items-center gap-1.5 text-sm font-semibold" title={k ? `KDIGO ${categoria}: ${k.texto}` : undefined}>
      {k && <span className={`size-2.5 rounded-sm ${k.dot}`} aria-hidden="true" />}
      {categoria}
    </span>
  );
}

// Distintivo de datos cruzados entre comunidades: "eCAP + DIRAYA".
export function CruzadoBadge({ fuentes }) {
  const regionales = fuentes.filter((f) => f.includes(" - "));
  return (
    <span
      className={`${CHIP} bg-violet-50 text-violet-800 ring-violet-200`}
      title={`Analíticas de varias comunidades integradas: ${regionales.join(" + ")}`}
    >
      <ArrowLeftRight className="size-3" aria-hidden="true" />
      Datos cruzados: {regionales.map((f) => f.split(" - ")[0]).join(" + ")}
    </span>
  );
}

export function Cargando({ texto = "Cargando…" }) {
  return (
    <div className="flex items-center justify-center gap-2 rounded-lg border border-line bg-white py-16 text-sm text-muted" role="status">
      <LoaderCircle className="size-5 animate-spin text-clinic-600" aria-hidden="true" />
      {texto}
    </div>
  );
}

export function ErrorPanel({ mensaje, onRetry }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-red-200 bg-red-50 px-6 py-10 text-center" role="alert">
      <CircleAlert className="size-7 text-red-700" aria-hidden="true" />
      <p className="max-w-xl text-sm text-red-900">{mensaje}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-2 rounded-md bg-white px-3 py-1.5 text-sm font-semibold text-red-800 ring-1 ring-red-300 hover:bg-red-100"
        >
          <RotateCw className="size-4" aria-hidden="true" />
          Reintentar
        </button>
      )}
    </div>
  );
}
