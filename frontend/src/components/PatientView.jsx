import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, BellRing, CircleCheck, ClipboardList, FileText, Lightbulb, ListChecks, PiggyBank } from "lucide-react";
import { api } from "../api.js";
import { ESTADO_RENAL, fecha, KDIGO, num, pct, SEXO } from "../format.js";
import NoteModal from "./NoteModal.jsx";
import RenalChart, { estiloOrigenes, Marca } from "./RenalChart.jsx";
import { Cargando, CruzadoBadge, ErrorPanel, GrupoTag, KdigoTag, RiesgoCvChip } from "./ui.jsx";

function Tarjeta({ titulo, icono: Icono, accion, children, className = "" }) {
  return (
    <section className={`rounded-lg border border-line bg-white shadow-xs ${className}`}>
      <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
        {Icono && <Icono className="size-4 text-clinic-600" aria-hidden="true" />}
        <h2 className="text-sm font-semibold text-ink">{titulo}</h2>
        <div className="ml-auto">{accion}</div>
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

function Dato({ etiqueta, valor, detalle }) {
  return (
    <div>
      <dt className="text-xs text-muted">{etiqueta}</dt>
      <dd className="text-lg font-semibold leading-tight text-ink">{valor}</dd>
      {detalle && <dd className="text-xs text-muted">{detalle}</dd>}
    </div>
  );
}

function OrigenTag({ origen, estilos }) {
  if (!origen) return <span className="text-muted">No informado</span>;
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <svg width="12" height="12" viewBox="0 0 14 14" aria-hidden="true">
        <Marca estilo={estilos[origen]} x={7} y={7} r={4.5} anillo={false} />
      </svg>
      {origen}
    </span>
  );
}

export default function PatientView({ id, sel, version, fuentes }) {
  const [estado, setEstado] = useState({ data: null, error: null });
  const [intento, setIntento] = useState(0);
  const [modal, setModal] = useState(false);
  const [prueba, setPrueba] = useState("TODAS");
  const cerrarModal = useCallback(() => setModal(false), []);

  useEffect(() => {
    const ctrl = new AbortController();
    setEstado((s) => ({ ...s, error: null }));
    api
      .pacient(id, sel, ctrl.signal)
      .then((data) => setEstado({ data, error: null }))
      .catch((e) => e.name !== "AbortError" && setEstado({ data: null, error: e.message }));
    return () => ctrl.abort();
  }, [id, sel.iss, version, intento]);

  const data = estado.data?.pacient.pacient_id === id ? estado.data : null;
  const origenes = useMemo(() => [...new Set((data?.analitiques ?? []).map((a) => a.origen).filter(Boolean))].sort(), [data]);
  // Color y forma por sistema de origen, estables en todo el cupo (no dependen de qué fuentes tenga cada paciente)
  const estilos = useMemo(
    () => estiloOrigenes([...new Set([...(fuentes ?? []), ...origenes])].sort((a, b) => a.localeCompare(b, "es", { sensitivity: "base" }))),
    [fuentes, origenes],
  );
  const pruebas = useMemo(() => [...new Set((data?.analitiques ?? []).map((a) => a.nom))].sort((a, b) => a.localeCompare(b, "es")), [data]);

  const volver = (
    <a href="#/" className="inline-flex items-center gap-1.5 text-sm font-semibold text-clinic-700 hover:underline">
      <ArrowLeft className="size-4" aria-hidden="true" />
      Volver al cupo
    </a>
  );
  if (estado.error) {
    return (
      <div className="space-y-4">
        {volver}
        <ErrorPanel mensaje={estado.error} onRetry={() => setIntento((n) => n + 1)} />
      </div>
    );
  }
  if (!data) return <Cargando texto="Cargando la ficha clínica…" />;

  const p = data.pacient;
  const historico = [...data.analitiques].reverse().filter((a) => prueba === "TODAS" || a.nom === prueba);
  const ahorros = [...p.accions_recomanades.filter((a) => a.nota).map((a) => ({ texto: a.nota, sobre: a.text })), ...p.avisos.map((t) => ({ texto: t }))];

  return (
    <div className="space-y-4">
      {volver}

      <section className="rounded-lg border border-line bg-white p-4 shadow-xs">
        <div className="flex flex-wrap items-start gap-x-6 gap-y-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
              <h1 className="text-xl font-semibold text-ink">{p.nom}</h1>
              <RiesgoCvChip p={p} prefijo="Riesgo CV: " />
              {p.dades_creuades && <CruzadoBadge fuentes={p.fonts_dades} />}
              {p.ben_tractat && (
                <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700">
                  <CircleCheck className="size-4" aria-hidden="true" />
                  Bien tratado
                </span>
              )}
            </div>
            <p className="mt-0.5 text-sm text-muted">
              {p.pacient_id} · {p.edat} años · {SEXO[p.sexe]}
            </p>
            <p className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-muted">
              Lista de trabajo: <GrupoTag p={p} /> · {p.puntuacio_prioritat} puntos del motor
            </p>
            <p className="mt-2 max-w-4xl text-sm text-ink">{p.resum}</p>
          </div>
          <button
            type="button"
            onClick={() => setModal(true)}
            className="inline-flex items-center gap-2 rounded-md bg-clinic-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-clinic-700"
          >
            <FileText className="size-4" aria-hidden="true" />
            Generar nota clínica y volante
          </button>
        </div>
        <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 border-t border-line pt-4 sm:grid-cols-3 lg:grid-cols-6">
          <Dato
            etiqueta="KDIGO"
            valor={<KdigoTag categoria={p.categoria_kdigo} riesgo={p.risc_kdigo} />}
            detalle={KDIGO[p.risc_kdigo] ? `${KDIGO[p.risc_kdigo].texto} · ${ESTADO_RENAL[p.estat_renal]}` : ESTADO_RENAL[p.estat_renal]}
          />
          <Dato etiqueta="FGe actual" valor={num(p.fge_actual)} detalle={`mL/min/1,73m² · ${data.meta.equacio_fge}`} />
          <Dato etiqueta="UACR actual" valor={p.uacr_actual == null ? "Sin dato" : num(p.uacr_actual)} detalle="mg/g" />
          <Dato etiqueta="Pendiente del FGe" valor={p.pendent_fge == null ? "—" : num(p.pendent_fge, 1)} detalle="mL/min/1,73m² por año" />
          <Dato etiqueta="KFRE a 5 años" valor={pct(p.kfre_5a)} detalle={p.kfre_5a == null ? "solo con FGe < 60 y UACR" : "riesgo de fallo renal"} />
          <Dato etiqueta="Riesgo CV a 10 años" valor={pct(p.risc_cv_percentatge)} detalle={p.escala_usada ?? "no calculable"} />
        </dl>
      </section>

      <div className="grid gap-4 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">
          <Tarjeta titulo="Evolución del FGe y de la albuminuria (4 años)" icono={ClipboardList}>
            <RenalChart series={data.series} llindars={data.llindars} pendiente={p.pendent_fge} fechaReferencia={data.meta.data_referencia} estilos={estilos} />
          </Tarjeta>

          <Tarjeta titulo={`Alertas activas (${p.alertes_actives.length})`} icono={BellRing}>
            {p.alertes_actives.length === 0 ? (
              <p className="text-sm text-muted">{p.ben_tractat ? "Sin alertas: tratamiento y objetivos correctos." : "Sin alertas activas."}</p>
            ) : (
              <ul className="space-y-3">
                {p.alertes_actives.map((a) => (
                  <li key={a.regla} className="rounded-md border-l-4 border-red-600 bg-red-50/60 px-3 py-2.5">
                    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                      <h3 className="text-sm font-semibold text-ink">{a.titol}</h3>
                      <span className="rounded bg-white px-1.5 py-0.5 text-[11px] font-medium text-muted ring-1 ring-line">{a.evidencia}</span>
                      <span className="tabular ml-auto text-xs text-muted">+{a.pes} puntos</span>
                    </div>
                    <p className="mt-1 text-sm text-ink">{a.motiu}</p>
                    {a.fonts.length > 0 && (
                      <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                        Datos de:
                        {a.fonts.map((f) => (
                          <OrigenTag key={f} origen={f} estilos={estilos} />
                        ))}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Tarjeta>

          <Tarjeta
            titulo={`Histórico de analíticas (${historico.length})`}
            icono={ClipboardList}
            accion={
              <label className="flex items-center gap-2 text-xs text-muted">
                Prueba
                <select value={prueba} onChange={(e) => setPrueba(e.target.value)} className="h-7 rounded border border-line bg-white px-1.5 text-xs text-ink">
                  <option value="TODAS">Todas</option>
                  {pruebas.map((n) => (
                    <option key={n}>{n}</option>
                  ))}
                </select>
              </label>
            }
          >
            <div className="-m-4 max-h-96 overflow-auto">
              <table className="w-full border-collapse text-left text-sm">
                <thead className="sticky top-0 bg-clinic-50 text-[11px] font-semibold uppercase tracking-wide text-muted">
                  <tr>
                    <th scope="col" className="px-4 py-2">Fecha</th>
                    <th scope="col" className="px-3 py-2">Prueba</th>
                    <th scope="col" className="px-3 py-2 text-right">Valor</th>
                    <th scope="col" className="px-3 py-2">Unidad</th>
                    <th scope="col" className="px-3 py-2">Sistema de origen</th>
                  </tr>
                </thead>
                <tbody>
                  {historico.map((a, i) => (
                    <tr key={i} className="border-t border-line">
                      <td className="tabular whitespace-nowrap px-4 py-1.5">{fecha(a.data)}</td>
                      <td className="px-3 py-1.5">{a.nom}</td>
                      <td className="tabular px-3 py-1.5 text-right font-semibold">{num(a.valor, Number.isInteger(a.valor) ? 0 : 2)}</td>
                      <td className="px-3 py-1.5 text-muted">{a.unitat}</td>
                      <td className="px-3 py-1.5 text-xs">
                        <OrigenTag origen={a.origen} estilos={estilos} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Tarjeta>
        </div>

        <div className="space-y-4">
          <Tarjeta titulo="Riesgo cardiovascular" icono={ClipboardList}>
            <div className="flex items-end gap-3">
              <p className="text-4xl font-semibold leading-none text-ink">{pct(p.risc_cv_percentatge)}</p>
              <RiesgoCvChip p={p} />
            </div>
            <p className="mt-1 text-xs text-muted">Categoría de la tabla 5 de la guía ESC 2021 (calibración de país de riesgo bajo).</p>
            <dl className="mt-3 space-y-2 text-sm">
              <div>
                <dt className="text-xs text-muted">Escala aplicada</dt>
                <dd className="font-medium text-ink">{p.escala_usada ?? (p.categoria_risc_cv ? "Sin escala (categoría directa)" : p.text_risc_cv)}</dd>
              </div>
              {p.rang_referencia_cv && (
                <div>
                  <dt className="text-xs text-muted">Rango de referencia aplicado</dt>
                  <dd className="text-ink">{p.rang_referencia_cv}</dd>
                </div>
              )}
              {p.nota_calibracio && (
                <div className="rounded-md bg-clinic-50 px-2.5 py-2 text-xs text-ink ring-1 ring-inset ring-line">
                  {p.nota_calibracio}. <span className="text-muted">Solo como referencia: no cambia la categoría.</span>
                </div>
              )}
              {p.risc_cv?.hf && <dd className="text-xs text-muted">Hipercolesterolemia familiar: riesgo alto sin necesidad de escala.</dd>}
              {p.risc_cv?.reclassificat_mrc && <dd className="text-xs text-muted">Categoría reclasificada al alza por ERC (matriz KDIGO).</dd>}
              {p.risc_cv?.ecv_establerta && <dd className="text-xs text-muted">Enfermedad cardiovascular establecida: riesgo muy alto sin necesidad de escala.</dd>}
              {p.objectius_pendents.length > 0 && (
                <div>
                  <dt className="text-xs text-muted">Objetivos pendientes</dt>
                  <dd>
                    <ul className="mt-0.5 list-disc space-y-0.5 pl-4 text-ink">
                      {p.objectius_pendents.map((o) => (
                        <li key={o}>{o}</li>
                      ))}
                    </ul>
                  </dd>
                </div>
              )}
            </dl>
          </Tarjeta>

          <Tarjeta titulo={`Plan sugerido (${p.accions_recomanades.length})`} icono={ListChecks}>
            {p.accions_recomanades.length === 0 ? (
              <p className="text-sm text-muted">Sin acciones pendientes.</p>
            ) : (
              <ol className="space-y-2.5">
                {p.accions_recomanades.map((a, i) => (
                  <li key={a.clau} className="flex gap-2.5 text-sm">
                    <span className="tabular grid size-5 shrink-0 place-items-center rounded-full bg-clinic-100 text-[11px] font-semibold text-clinic-800">{i + 1}</span>
                    <span>
                      <span className="text-ink">{a.text}</span> <span className="whitespace-nowrap text-xs text-muted">({a.evidencia})</span>
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </Tarjeta>

          {ahorros.length > 0 && (
            <Tarjeta titulo="Ahorro de analíticas y anti-inercia" icono={PiggyBank}>
              <ul className="space-y-2.5">
                {ahorros.map((a, i) => (
                  <li key={i} className="flex gap-2 rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-950 ring-1 ring-inset ring-emerald-200">
                    <Lightbulb className="mt-0.5 size-4 shrink-0 text-emerald-700" aria-hidden="true" />
                    <span>
                      {a.texto}
                      {a.sobre && <span className="mt-0.5 block text-xs text-emerald-800">Al aplicar: {a.sobre}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            </Tarjeta>
          )}

          <Tarjeta titulo="Diagnósticos y tratamiento" icono={ClipboardList}>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">Diagnósticos</h3>
            <ul className="mt-1 space-y-1 text-sm">
              {data.diagnostics.length === 0 && <li className="text-muted">Sin diagnósticos crónicos registrados.</li>}
              {data.diagnostics.map((d) => (
                <li key={d.codi_ciap2} className="flex justify-between gap-3">
                  <span className="text-ink">{d.nom}</span>
                  <span className="whitespace-nowrap text-xs text-muted">
                    {d.codi_ciap2} · {d.codi_cie10} · {fecha(d.data).slice(6)}
                  </span>
                </li>
              ))}
            </ul>
            <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-muted">Tratamiento activo</h3>
            <ul className="mt-1 space-y-1 text-sm">
              {data.medicacions.length === 0 && <li className="text-muted">Sin tratamiento registrado.</li>}
              {data.medicacions.map((m) => (
                <li key={m.codi_atc + m.data_inici} className="flex justify-between gap-3">
                  <span className="text-ink">{m.nom}</span>
                  <span className="whitespace-nowrap text-xs text-muted">
                    {m.grup} · desde {fecha(m.data_inici).slice(3)}
                  </span>
                </li>
              ))}
            </ul>
            <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-muted">Fuentes integradas (HL7 FHIR)</h3>
            <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm">
              {origenes.map((o) => (
                <li key={o}>
                  <OrigenTag origen={o} estilos={estilos} />
                </li>
              ))}
            </ul>
          </Tarjeta>
        </div>
      </div>

      {modal && <NoteModal paciente={p} onClose={cerrarModal} />}
    </div>
  );
}
