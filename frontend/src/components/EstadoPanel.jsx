import { useState } from "react";
import { CalendarClock, CalendarPlus, CircleCheck, History, RotateCcw, UserRound } from "lucide-react";
import { api } from "../api.js";
import { ESTADOS, fecha, fechaHora, textoEstado } from "../format.js";
import { lanzamiento } from "../launch.js";
import { EstadoChip } from "./ui.jsx";

// Profesional del contexto de lanzamiento: es quien firma cada cambio en el log de auditoría.
const PROFESIONAL = lanzamiento?.profesional ? { id: lanzamiento.fhirUser, nom: lanzamiento.profesional, rol: lanzamiento.rol } : null;

function manana(iso) {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
}

function enUnMes(iso) {
  const d = new Date(`${iso}T12:00:00`);
  d.setMonth(d.getMonth() + 1);
  return d.toISOString().slice(0, 10);
}

const BOTONES = [
  { estat: "citat", icono: CalendarPlus, texto: "Citado" },
  { estat: "revisat", icono: CircleCheck, texto: "Revisado" },
];

// Estado de la alerta del paciente y su historial de cambios. Los pacientes «Citado», «Revisado» o «Pospuesto»
// salen de «Hoy» pero siguen en el cupo; si llega una alerta nueva, el add-on los devuelve a «Pendiente».
export default function EstadoPanel({ id, sel, estado, auditoria, fechaReferencia, onCambiado }) {
  const [fins, setFins] = useState(() => enUnMes(fechaReferencia));
  const [enviando, setEnviando] = useState(null);
  const [error, setError] = useState(null);
  const actual = estado ?? { estat: "pendent" };

  const cambiar = async (estat) => {
    setEnviando(estat);
    setError(null);
    try {
      const r = await api.cambiarEstado(id, sel, { estat, fins: estat === "posposat" ? fins : null, profesional: PROFESIONAL });
      onCambiado(r);
    } catch (e) {
      setError(e.message);
    } finally {
      setEnviando(null);
    }
  };

  return (
    <section className="rounded-lg border border-line bg-white shadow-xs" aria-label="Estado de la alerta">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-line px-4 py-2.5">
        <CalendarClock className="size-4 text-clinic-600" aria-hidden="true" />
        <h2 className="text-sm font-semibold text-ink">Estado de la alerta</h2>
        <EstadoChip estado={actual} />
        {actual.quan && !actual.vencut && (
          <span className="text-xs text-muted">
            {fechaHora(actual.quan)} · {actual.qui}
          </span>
        )}
      </div>
      <div className="space-y-3 p-4">
        {PROFESIONAL ? (
          <>
            <div className="flex flex-wrap items-end gap-2">
              {BOTONES.map(({ estat, icono: Icono, texto }) => (
                <button
                  key={estat}
                  type="button"
                  disabled={enviando !== null || actual.estat === estat}
                  onClick={() => cambiar(estat)}
                  className="inline-flex h-9 items-center gap-1.5 rounded-md px-3 text-sm font-semibold text-clinic-800 ring-1 ring-inset ring-line hover:bg-clinic-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Icono className="size-4" aria-hidden="true" />
                  {texto}
                </button>
              ))}
              <span className="flex items-end gap-1.5">
                <label className="flex flex-col gap-0.5 text-xs text-muted">
                  Posponer hasta
                  <input
                    type="date"
                    value={fins}
                    min={manana(fechaReferencia)}
                    onChange={(e) => setFins(e.target.value)}
                    className="h-9 rounded-md border border-line bg-white px-2 text-sm text-ink"
                  />
                </label>
                <button
                  type="button"
                  disabled={enviando !== null || !fins}
                  onClick={() => cambiar("posposat")}
                  className="inline-flex h-9 items-center rounded-md px-3 text-sm font-semibold text-clinic-800 ring-1 ring-inset ring-line hover:bg-clinic-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Posponer
                </button>
              </span>
              {actual.estat !== "pendent" && (
                <button
                  type="button"
                  disabled={enviando !== null}
                  onClick={() => cambiar("pendent")}
                  className="inline-flex h-9 items-center gap-1.5 rounded-md px-3 text-sm font-semibold text-muted hover:bg-clinic-50 disabled:opacity-50"
                >
                  <RotateCcw className="size-4" aria-hidden="true" />
                  Volver a «Pendiente»
                </button>
              )}
            </div>
            <p className="flex items-center gap-1.5 text-xs text-muted">
              <UserRound className="size-3.5" aria-hidden="true" />
              Los cambios se registran a nombre de {PROFESIONAL.nom} (contexto de lanzamiento de la estación). Fecha de referencia: {fecha(fechaReferencia)}.
            </p>
          </>
        ) : (
          <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900 ring-1 ring-inset ring-amber-200">
            Para cambiar el estado, abra CardioAlert AP desde la estación clínica: cada cambio se audita con el profesional que la estación indica al
            abrir el add-on.
          </p>
        )}
        {error && (
          <p className="text-sm text-red-700" role="alert">
            {error}
          </p>
        )}
        <div>
          <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
            <History className="size-3.5" aria-hidden="true" />
            Historial de cambios (auditoría)
          </h3>
          {auditoria.length === 0 ? (
            <p className="mt-1 text-sm text-muted">Sin cambios registrados: el paciente está «Pendiente».</p>
          ) : (
            <ul className="mt-1 divide-y divide-line text-sm">
              {auditoria.map((a, i) => (
                <li key={i} className="flex flex-wrap gap-x-3 py-1.5">
                  <span className="tabular text-xs text-muted">{fechaHora(a.quan)}</span>
                  <span className="text-ink">
                    {ESTADOS[a.anterior]?.texto ?? a.anterior} → <strong className="font-semibold">{textoEstado({ estat: a.estat, fins: a.fins })}</strong>
                  </span>
                  <span className="text-xs text-muted">{a.qui?.nom}</span>
                  {a.motiu && <span className="w-full text-xs text-amber-800">{a.motiu}</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
