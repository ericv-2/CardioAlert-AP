import { useMemo } from "react";
import { Download, FlaskConical } from "lucide-react";
import { api } from "../api.js";
import { fecha, num, SEXO } from "../format.js";
import { Cargando, ErrorPanel, EstadoChip } from "./ui.jsx";

// Vista «Pruebas pendientes»: pacientes con UACR o creatinina pendiente (reglas uacr_falta y creatinina_falta).
// Estas alertas no cuentan para el orden de «Hoy»: se resuelven de una vez con una petición conjunta.
export default function PruebasView({ cupo, sel, onRetry }) {
  const { data, error } = cupo;
  const filas = useMemo(() => {
    const out = [];
    for (const p of data?.pacients ?? []) {
      for (const prueba of p.proves_pendents ?? []) out.push({ p, prueba });
    }
    // Primero las que nunca se han hecho; después, de más a menos meses sin la prueba
    return out.sort(
      (a, b) =>
        (a.prueba.mesos_sense != null) - (b.prueba.mesos_sense != null) ||
        (b.prueba.mesos_sense ?? 0) - (a.prueba.mesos_sense ?? 0) ||
        a.p.pacient_id.localeCompare(b.p.pacient_id),
    );
  }, [data]);

  if (error) return <ErrorPanel mensaje={error} onRetry={onRetry} />;
  if (!data) return <Cargando texto="Leyendo el cupo de la estación clínica y calculando…" />;

  const pacientes = new Set(filas.map((f) => f.p.pacient_id)).size;
  const porPrueba = filas.reduce((acc, f) => ({ ...acc, [f.prueba.prova]: (acc[f.prueba.prova] ?? 0) + 1 }), {});
  const boton =
    "inline-flex h-9 items-center gap-2 rounded-md bg-white px-3 text-sm font-semibold text-clinic-700 ring-1 ring-inset ring-line hover:bg-clinic-50";

  return (
    <section className="rounded-lg border border-line bg-white shadow-xs" aria-label="Pruebas pendientes">
      <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
        <FlaskConical className="size-5 text-amber-700" aria-hidden="true" />
        <div className="mr-auto">
          <h1 className="text-base font-semibold text-ink">
            Pruebas pendientes: {num(pacientes)} pacientes, {num(filas.length)} pruebas
          </h1>
          <p className="text-xs text-muted">
            {Object.entries(porPrueba)
              .map(([n, c]) => `${n}: ${num(c)}`)
              .join(" · ")}
            {filas.length > 0 && " · "}
            Pacientes con DM2, HTA, ERC u otra patología crónica sin la prueba de control en el plazo de rules.yaml. No cuentan para el orden de
            «Hoy»: se piden juntas.
          </p>
        </div>
        <a href={api.pruebasUrl(sel, "csv")} download="pruebas_pendientes.csv" className={boton}>
          <Download className="size-4" aria-hidden="true" />
          CSV
        </a>
        <a href={api.pruebasUrl(sel, "xlsx")} download="pruebas_pendientes.xlsx" className={boton}>
          <Download className="size-4" aria-hidden="true" />
          Petición conjunta (Excel)
        </a>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[860px] border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-line bg-clinic-50 text-[11px] font-semibold uppercase tracking-wide text-muted">
              <th scope="col" className="px-4 py-2.5">Paciente</th>
              <th scope="col" className="px-3 py-2.5">Prueba</th>
              <th scope="col" className="px-3 py-2.5">Desde cuándo</th>
              <th scope="col" className="px-3 py-2.5">Motivo</th>
              <th scope="col" className="px-3 py-2.5">Estado de la alerta</th>
            </tr>
          </thead>
          <tbody>
            {filas.map(({ p, prueba }) => (
              <tr key={`${p.pacient_id}-${prueba.regla}`} className="border-b border-line align-top last:border-b-0 hover:bg-clinic-50">
                <td className="px-4 py-2.5">
                  <a href={`#/paciente/${p.pacient_id}`} className="font-semibold text-clinic-700 hover:underline">
                    {p.nom}
                  </a>
                  <p className="text-xs text-muted">
                    {p.pacient_id} · {p.edat} años · {SEXO[p.sexe]}
                  </p>
                </td>
                <td className="px-3 py-2.5">
                  <p className="font-medium text-ink">{prueba.prova}</p>
                  <p className="text-xs text-muted">{prueba.peticio}</p>
                </td>
                <td className="px-3 py-2.5">
                  {prueba.ultima_data ? (
                    <>
                      <p className="tabular font-medium text-ink">Hace {num(prueba.mesos_sense)} meses</p>
                      <p className="text-xs text-muted">
                        Última: {fecha(prueba.ultima_data)}
                        {prueba.origen && ` · ${prueba.origen}`}
                      </p>
                    </>
                  ) : (
                    <p className="font-medium text-red-800">Nunca registrada</p>
                  )}
                </td>
                <td className="px-3 py-2.5 text-ink">
                  {prueba.diagnostics.join(" + ")}
                  <p className="text-xs text-muted">Control cada {prueba.max_mesos} meses</p>
                </td>
                <td className="px-3 py-2.5">
                  <EstadoChip estado={data.estats?.[p.pacient_id]} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filas.length === 0 && <p className="px-4 py-10 text-center text-sm text-muted">No hay pruebas pendientes en el cupo.</p>}
      </div>
    </section>
  );
}
