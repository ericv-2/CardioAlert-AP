import { useMemo, useRef, useState } from "react";
import { fecha, num } from "../format.js";

// Evolución del FGe y del UACR: dos paneles con el mismo eje de tiempo (nunca dos escalas en un panel).
// La línea es neutra; el color y la forma de cada punto indican el sistema de origen del dato.
const ORIGEN_ESTILOS = [
  { color: "#2a78d6", forma: "circulo" },
  { color: "#eb6834", forma: "rombo" },
  { color: "#1baf7a", forma: "cuadrado" },
];
const OTRO = { color: "#6b7785", forma: "circulo" };
const TINTA = "#1b2733";
const TENUE = "#5b6b7b";
const REJILLA = "#e6ebf0";
const LINEA = "#4a5866";

const W = 860;
const M = { top: 34, right: 96, bottom: 12, left: 46 };
const ALTO_PANEL = 190;
const ALTO_EJE = 26;

const dia = (iso) => Date.parse(`${iso}T00:00:00Z`);

export function estiloOrigenes(origenes) {
  const mapa = {};
  origenes.forEach((o, i) => (mapa[o] = ORIGEN_ESTILOS[i] ?? OTRO));
  return mapa;
}

export function Marca({ estilo, x, y, r = 5, anillo = true }) {
  const comun = { fill: estilo.color, stroke: anillo ? "#fff" : "none", strokeWidth: 2 };
  if (estilo.forma === "rombo") return <rect x={x - r} y={y - r} width={2 * r} height={2 * r} transform={`rotate(45 ${x} ${y})`} {...comun} />;
  if (estilo.forma === "cuadrado") return <rect x={x - r + 0.5} y={y - r + 0.5} width={2 * r - 1} height={2 * r - 1} rx={1} {...comun} />;
  return <circle cx={x} cy={y} r={r} {...comun} />;
}

function ticksLimpios(max, objetivo = 4) {
  const bruto = max / objetivo;
  const pot = 10 ** Math.floor(Math.log10(bruto));
  const paso = [1, 2, 2.5, 5, 10].map((m) => m * pot).find((p) => p >= bruto);
  const ticks = [];
  const n = Math.ceil(max / paso - 1e-9); // el último tick siempre cubre el valor máximo
  for (let i = 0; i <= n; i++) ticks.push(Math.round(i * paso * 100) / 100);
  return ticks;
}

function Panel({ titulo, unidad, nota, serie, umbral, textoUmbral, y0, x, estilos, principal, activo, sinDatos }) {
  const valores = serie.map((m) => m.valor);
  const tope = Math.max(...valores, umbral * 1.5, 1);
  const ticks = ticksLimpios(tope);
  const max = ticks[ticks.length - 1];
  const y = (v) => y0 + M.top + (1 - v / max) * (ALTO_PANEL - M.top - M.bottom);
  const camino = serie.map((m, i) => `${i ? "L" : "M"}${x(dia(m.data)).toFixed(1)},${y(m.valor).toFixed(1)}`).join(" ");

  return (
    <g>
      <text x={0} y={y0 + 13} fontSize="13" fontWeight="600" fill={TINTA}>
        {titulo} <tspan fontWeight="400" fill={TENUE}>· {unidad}</tspan>
      </text>
      {nota && (
        <text x={W - M.right} y={y0 + 13} fontSize="12" fill={TENUE} textAnchor="end">
          {nota}
        </text>
      )}
      {ticks.map((t) => (
        <g key={t}>
          <line x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)} stroke={REJILLA} strokeWidth="1" />
          <text x={M.left - 8} y={y(t) + 4} fontSize="11" fill={TENUE} textAnchor="end" style={{ fontVariantNumeric: "tabular-nums" }}>
            {num(t, Number.isInteger(t) ? 0 : 1)}
          </text>
        </g>
      ))}
      {/* Umbral del protocolo (config/rules.yaml): referencia, no dato */}
      <line x1={M.left} x2={W - M.right} y1={y(umbral)} y2={y(umbral)} stroke="#b4232a" strokeWidth="1" />
      <text x={W - M.right + 6} y={y(umbral) + 4} fontSize="11" fill="#8f1d22">
        {textoUmbral}
      </text>
      {sinDatos ? (
        <text x={(M.left + W - M.right) / 2} y={y0 + ALTO_PANEL / 2 + 10} fontSize="13" fill={TENUE} textAnchor="middle">
          {sinDatos}
        </text>
      ) : (
        <>
          <path d={camino} fill="none" stroke={LINEA} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
          {serie.map((m, i) => {
            const cx = x(dia(m.data));
            const cy = y(m.valor);
            const cruzado = m.origen && m.origen !== principal;
            const esUltimo = i === serie.length - 1;
            return (
              <g key={`${m.data}-${i}`}>
                <Marca estilo={estilos[m.origen] ?? OTRO} x={cx} y={cy} r={activo === m.data ? 6.5 : 5} />
                {/* Etiquetas selectivas: el dato que llega de otro sistema y el último valor */}
                {cruzado && (
                  <text x={cx} y={cy - 12} fontSize="11" fontWeight="600" fill={TINTA} textAnchor="middle">
                    {m.origen.split(" - ")[0]}
                  </text>
                )}
                {esUltimo && (
                  <text x={cx + 10} y={cy + (Math.abs(cy - y(umbral)) < 12 ? -8 : 4)} fontSize="12" fontWeight="600" fill={TINTA}>
                    {num(m.valor)}
                  </text>
                )}
              </g>
            );
          })}
        </>
      )}
    </g>
  );
}

export default function RenalChart({ series, llindars, pendiente, fechaReferencia, estilos }) {
  const ref = useRef(null);
  const [hover, setHover] = useState(null); // fecha ISO resaltada
  const { fge, uacr } = series;
  // Leyenda: solo los sistemas que aportan datos a esta gráfica
  const origenes = useMemo(() => Object.keys(estilos).filter((o) => [...fge, ...uacr].some((m) => m.origen === o)), [estilos, fge, uacr]);

  const fin = dia(fechaReferencia);
  const todas = [...fge, ...uacr].map((m) => dia(m.data));
  const inicio = Math.min(fin - 4 * 365.25 * 864e5, ...todas);
  const x = (t) => M.left + ((t - inicio) / (fin - inicio)) * (W - M.left - M.right);
  const anyos = [];
  for (let a = new Date(inicio).getUTCFullYear() + 1; a <= new Date(fin).getUTCFullYear(); a++) anyos.push(a);

  const fechas = useMemo(() => [...new Set([...fge, ...uacr].map((m) => m.data))].sort(), [fge, uacr]);
  // Sistema de origen habitual del paciente: los puntos de cualquier otro se etiquetan sobre la gráfica
  const principal = useMemo(() => {
    const n = {};
    [...fge, ...uacr].forEach((m) => m.origen && (n[m.origen] = (n[m.origen] ?? 0) + 1));
    return Object.entries(n).sort((a, b) => b[1] - a[1])[0]?.[0];
  }, [fge, uacr]);

  const alto = 2 * ALTO_PANEL + ALTO_EJE + 14;
  const yPanel2 = ALTO_PANEL + 14;

  function mover(e) {
    const caja = ref.current.getBoundingClientRect();
    const px = ((e.clientX - caja.left) / caja.width) * W;
    let mejor = null;
    for (const f of fechas) if (mejor == null || Math.abs(x(dia(f)) - px) < Math.abs(x(dia(mejor)) - px)) mejor = f;
    setHover(mejor);
  }

  const enFecha = hover && {
    fge: fge.find((m) => m.data === hover),
    uacr: uacr.find((m) => m.data === hover),
  };
  const hx = hover ? x(dia(hover)) : 0;

  if (fechas.length === 0) return <p className="py-8 text-center text-sm text-muted">Sin creatinina ni UACR registrados.</p>;

  return (
    <div>
      <ul className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink" aria-label="Sistema de origen de cada dato">
        <li className="text-muted">Origen del dato:</li>
        {origenes.map((o) => (
          <li key={o} className="flex items-center gap-1.5">
            <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
              <Marca estilo={estilos[o]} x={7} y={7} r={4.5} anillo={false} />
            </svg>
            {o}
          </li>
        ))}
        <li className="flex items-center gap-1.5 text-muted">
          <span className="inline-block h-px w-5 bg-[#b4232a]" aria-hidden="true" />
          Umbral del protocolo
        </li>
      </ul>
      <div className="relative">
        <svg
          ref={ref}
          viewBox={`0 0 ${W} ${alto}`}
          className="block h-auto w-full touch-none select-none"
          role="img"
          aria-label="Evolución del filtrado glomerular y de la albuminuria. Todos los valores figuran en la tabla del histórico de analíticas."
          onPointerMove={mover}
          onPointerLeave={() => setHover(null)}
        >
          {anyos.map((a) => {
            const xa = x(Date.UTC(a, 0, 1));
            return (
              <g key={a}>
                <line x1={xa} x2={xa} y1={M.top} y2={alto - ALTO_EJE} stroke={REJILLA} strokeWidth="1" />
                <text x={xa} y={alto - 8} fontSize="11" fill={TENUE} textAnchor="middle">
                  {a}
                </text>
              </g>
            );
          })}
          {hover && <line x1={hx} x2={hx} y1={M.top - 6} y2={alto - ALTO_EJE} stroke={TENUE} strokeWidth="1" />}
          <Panel
            titulo="Filtrado glomerular estimado (FGe)"
            unidad="mL/min/1,73m²"
            nota={pendiente != null ? `Pendiente: ${num(pendiente, 1)} mL/min/1,73m² por año` : null}
            serie={fge}
            umbral={llindars.fge}
            textoUmbral={`ERC si < ${llindars.fge}`}
            y0={0}
            x={x}
            estilos={estilos}
            principal={principal}
            activo={hover}
            sinDatos={fge.length ? null : "Sin creatinina registrada"}
          />
          <Panel
            titulo="Albuminuria (UACR)"
            unidad="mg/g"
            serie={uacr}
            umbral={llindars.uacr}
            textoUmbral={`Elevada si ≥ ${llindars.uacr}`}
            y0={yPanel2}
            x={x}
            estilos={estilos}
            principal={principal}
            activo={hover}
            sinDatos={uacr.length ? null : "Sin UACR registrado: albuminuria no valorada"}
          />
        </svg>
        {hover && (
          <div
            className="pointer-events-none absolute top-0 z-10 w-56 rounded-md border border-line bg-white p-2.5 text-xs shadow-lg"
            style={hx > W * 0.6 ? { right: `${100 - (hx / W) * 100 + 1.5}%` } : { left: `${(hx / W) * 100 + 1.5}%` }}
          >
            <p className="mb-1 font-semibold text-ink">{fecha(hover)}</p>
            {[
              ["FGe", enFecha.fge, "mL/min/1,73m²"],
              ["UACR", enFecha.uacr, "mg/g"],
            ].map(([nombre, m, unidad]) => (
              <div key={nombre} className="flex items-baseline justify-between gap-2 py-0.5">
                <span className="text-muted">{nombre}</span>
                {m ? (
                  <span className="text-right">
                    <strong className="tabular text-sm font-semibold text-ink">{num(m.valor)}</strong> <span className="text-muted">{unidad}</span>
                    <span className="mt-0.5 flex items-center justify-end gap-1 text-muted">
                      <svg width="10" height="10" viewBox="0 0 14 14" aria-hidden="true">
                        <Marca estilo={estilos[m.origen] ?? OTRO} x={7} y={7} r={5} anillo={false} />
                      </svg>
                      {m.origen ?? "Origen no informado"}
                    </span>
                  </span>
                ) : (
                  <span className="text-muted">sin dato ese día</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
