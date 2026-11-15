import { useEffect, useState } from "react";
import { Bot, History, RotateCw } from "lucide-react";
import { api } from "../api.js";
import { fechaHora, num } from "../format.js";
import { Cargando, ErrorPanel } from "./ui.jsx";

// Vista «Registro de actividad»: cada acción del add-on como recurso FHIR AuditEvent (quién, cuándo, qué
// paciente, qué acción y desde qué estación). Filtros por paciente, profesional y tipo de acción.
const campo = "h-9 rounded-md border border-line bg-white px-2 text-sm text-ink";

export default function ActividadView({ sel, version }) {
  const [filtros, setFiltros] = useState({ paciente: "", profesional: "", tipo: "" });
  const [pacienteEscrito, setPacienteEscrito] = useState("");
  const [estado, setEstado] = useState({ data: null, error: null });
  const [intento, setIntento] = useState(0);

  // El paciente se aplica al dejar de escribir
  useEffect(() => {
    const t = setTimeout(() => setFiltros((f) => ({ ...f, paciente: pacienteEscrito.trim() })), 400);
    return () => clearTimeout(t);
  }, [pacienteEscrito]);

  useEffect(() => {
    const ctrl = new AbortController();
    api
      .actividad(sel, { ...filtros, limit: 500 }, ctrl.signal)
      .then((data) => setEstado({ data, error: null }))
      .catch((e) => e.name !== "AbortError" && setEstado({ data: null, error: e.message }));
    return () => ctrl.abort();
  }, [sel, filtros, version, intento]);

  // Refresco ligero mientras se mira la vista (llegan notificaciones y recálculos automáticos)
  useEffect(() => {
    const reloj = setInterval(() => !document.hidden && setIntento((n) => n + 1), 5000);
    return () => clearInterval(reloj);
  }, []);

  if (estado.error) return <ErrorPanel mensaje={estado.error} onRetry={() => setIntento((n) => n + 1)} />;
  const data = estado.data;
  if (!data) return <Cargando texto="Leyendo el registro de actividad…" />;

  return (
    <section className="rounded-lg border border-line bg-white shadow-xs" aria-label="Registro de actividad">
      <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
        <History className="size-5 text-clinic-600" aria-hidden="true" />
        <div className="mr-auto">
          <h1 className="text-base font-semibold text-ink">Registro de actividad: {num(data.total)} entradas</h1>
          <p className="text-sm text-muted">
            Cada acción queda como recurso FHIR AuditEvent, separado por estación clínica ({data.servidor}).{" "}
            <a className="font-semibold text-clinic-700 underline" href={api.actividadFhirUrl(sel, filtros)} target="_blank" rel="noreferrer">
              Ver en FHIR
            </a>
          </p>
        </div>
        <button
          type="button"
          onClick={() => setIntento((n) => n + 1)}
          className="inline-flex h-9 items-center gap-2 rounded-md bg-white px-3 text-sm font-semibold text-clinic-700 ring-1 ring-inset ring-line hover:bg-clinic-50"
        >
          <RotateCw className="size-4" aria-hidden="true" />
          Actualizar
        </button>
      </div>
      <div className="flex flex-wrap items-end gap-3 border-b border-line bg-clinic-50/40 px-4 py-3">
        <label className="text-xs font-semibold text-muted">
          Paciente
          <input value={pacienteEscrito} onChange={(e) => setPacienteEscrito(e.target.value)} placeholder="P003" className={`${campo} mt-1 block w-32`} />
        </label>
        <label className="text-xs font-semibold text-muted">
          Profesional
          <select value={filtros.profesional} onChange={(e) => setFiltros((f) => ({ ...f, profesional: e.target.value }))} className={`${campo} mt-1 block`}>
            <option value="">Todos</option>
            {data.professionals.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nom}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs font-semibold text-muted">
          Acción
          <select value={filtros.tipo} onChange={(e) => setFiltros((f) => ({ ...f, tipo: e.target.value }))} className={`${campo} mt-1 block`}>
            <option value="">Todas</option>
            {data.tipus.map((t) => (
              <option key={t.id} value={t.id}>
                {t.text}
              </option>
            ))}
          </select>
        </label>
      </div>
      {data.entrades.length === 0 ? (
        <p className="px-4 py-10 text-center text-sm text-muted">No hay actividad con estos filtros.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-clinic-50 text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-2 font-semibold">Fecha y hora</th>
                <th className="px-4 py-2 font-semibold">Acción</th>
                <th className="px-4 py-2 font-semibold">Quién</th>
                <th className="px-4 py-2 font-semibold">Paciente</th>
                <th className="px-4 py-2 font-semibold">Detalle</th>
                <th className="px-4 py-2 font-semibold">Estación</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.entrades.map((e) => (
                <tr key={e.id} className={e.resultat !== "0" ? "bg-amber-50" : undefined}>
                  <td className="whitespace-nowrap px-4 py-2 tabular-nums text-muted">{fechaHora(e.quan)}</td>
                  <td className="px-4 py-2 font-medium text-ink">{e.tipus_text}</td>
                  <td className="px-4 py-2">
                    <span className="inline-flex items-center gap-1">
                      {e.automatic && <Bot className="size-4 text-muted" aria-label="Automático" />}
                      {e.qui}
                    </span>
                  </td>
                  <td className="px-4 py-2">
                    {e.pacient ? (
                      <a className="font-semibold text-clinic-700 underline" href={`#/paciente/${encodeURIComponent(e.pacient)}`}>
                        {e.pacient}
                      </a>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                  <td className="max-w-xl px-4 py-2 text-ink">{e.detall ?? "—"}</td>
                  <td className="px-4 py-2 text-muted">{e.estacio}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
