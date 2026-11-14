import { ArrowLeftRight, CircleAlert, LoaderCircle, RotateCw } from "lucide-react";
import { CATEGORIA_CV, KDIGO, NIVEL } from "../format.js";

const CHIP = "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ring-inset";

export function NivelChip({ nivel, largo = false }) {
  const n = NIVEL[nivel];
  if (!n) return null;
  return (
    <span className={`${CHIP} ${n.chip}`} title={n.largo}>
      <span className={`size-2 rounded-full ${n.dot}`} aria-hidden="true" />
      {largo ? `${n.largo} (${n.texto})` : n.texto}
    </span>
  );
}

export function CategoriaCvChip({ categoria }) {
  if (!categoria) return <span className="text-xs text-muted">No calculable</span>;
  return <span className={`${CHIP} ${CATEGORIA_CV[categoria] ?? "bg-slate-100 text-slate-700 ring-slate-200"}`}>{categoria}</span>;
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
