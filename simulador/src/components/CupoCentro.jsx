import { useState } from "react";
import { Building2, CircleCheck, LoaderCircle, TriangleAlert } from "lucide-react";
import { activarCupo, fhirBase } from "../historia.js";
import { num } from "../format.js";

// Configuración → Cupo / centro: qué cupo de pacientes tiene abierto la estación. Los datos son de la
// estación: su servidor FHIR sirve siempre los pacientes del cupo activo (también al add-on, si hay uno).
export default function CupoCentro({ cupos, onCambio }) {
  const [trabajando, setTrabajando] = useState(false);
  const [error, setError] = useState(null);
  const lista = cupos.data?.cupos ?? [];
  const activo = lista.find((c) => c.id === cupos.data?.activo) ?? null;

  async function cambiar(id) {
    if (id === activo?.id) return;
    setTrabajando(true);
    setError(null);
    try {
      onCambio(await activarCupo(id));
    } catch (e) {
      setError(e.message);
    } finally {
      setTrabajando(false);
    }
  }

  return (
    <section className="rounded-md border border-slate-300 bg-white" aria-labelledby="cupo-centro-titulo">
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 bg-slate-100 px-4 py-2.5">
        <Building2 className="size-4 text-teal-700" aria-hidden="true" />
        <h2 id="cupo-centro-titulo" className="text-sm font-semibold text-slate-900">
          Cupo / centro
        </h2>
        {activo && (
          <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-900 ring-1 ring-inset ring-emerald-300">
            <CircleCheck className="size-3.5" aria-hidden="true" />
            Activo: {activo.nombre} ({num(activo.pacientes)})
          </span>
        )}
      </div>
      <div className="space-y-3 p-4">
        {cupos.error ? (
          <p className="text-sm text-red-800" role="alert">{cupos.error}</p>
        ) : !cupos.data ? (
          <p className="text-sm text-slate-500" role="status">Cargando los cupos…</p>
        ) : (
          <>
            <div>
              <label htmlFor="sel-cupo" className="block text-sm font-semibold text-slate-900">
                Cupo / centro
              </label>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <select
                  id="sel-cupo"
                  value={activo?.id ?? ""}
                  disabled={trabajando}
                  onChange={(e) => cambiar(e.target.value)}
                  aria-describedby="cupo-ayuda"
                  className="h-9 min-w-72 rounded border border-slate-400 bg-white px-2.5 text-sm text-slate-900 disabled:opacity-60"
                >
                  {lista.map((c) => (
                    <option key={c.id} value={c.id} disabled={c.pacientes === 0}>
                      {c.nombre} · {c.centro} · {c.pacientes ? `${num(c.pacientes)} pacientes` : "sin datos"}
                    </option>
                  ))}
                </select>
                {trabajando && (
                  <span className="flex items-center gap-1.5 text-sm text-slate-600" role="status">
                    <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                    Cambiando de cupo…
                  </span>
                )}
              </div>
              <p id="cupo-ayuda" className="mt-1.5 max-w-3xl text-sm text-slate-600">
                {activo?.descripcion} La agenda y la historia clínica muestran los pacientes del cupo activo, y el servidor FHIR de la estación (
                <span className="break-all font-mono text-xs">{fhirBase()}</span>) sirve esos mismos datos a los add-ons instalados.
              </p>
            </div>
            {lista.some((c) => c.pacientes === 0) && (
              <p className="text-sm text-slate-600">
                {lista.filter((c) => c.pacientes === 0).map((c) => (
                  <span key={c.id} className="block">
                    {c.nombre}: sin datos. Para generarlos: <span className="font-mono text-xs">{c.generar}</span>
                  </span>
                ))}
              </p>
            )}
            {error && (
              <p className="flex items-start gap-2 rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-900" role="alert">
                <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                <span>No se ha cambiado de cupo. {error}</span>
              </p>
            )}
          </>
        )}
      </div>
    </section>
  );
}
