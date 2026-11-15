import { useEffect, useState } from "react";
import { Activity, AppWindow, ExternalLink, Info, LoaderCircle, OctagonAlert, RotateCw, TriangleAlert, Unplug } from "lucide-react";
import { llamarPatientView, nombreAddon, peticionPatientView, servicioPatientView } from "../integracion.js";

// Panel lateral de apoyo a la decisión: solo existe con un add-on instalado. Al abrir un paciente lanza el
// hook patient-view de CDS Hooks y pinta las tarjetas que devuelve el add-on. Aquí no hay lógica clínica.

const INDICADOR = {
  critical: { texto: "Alerta clínica urgente", icono: OctagonAlert, caja: "border-red-300 bg-red-50", barra: "bg-red-600", tono: "text-red-800" },
  warning: { texto: "Aviso", icono: TriangleAlert, caja: "border-amber-300 bg-amber-50", barra: "bg-amber-500", tono: "text-amber-900" },
  info: { texto: "Informativo", icono: Info, caja: "border-sky-200 bg-sky-50", barra: "bg-sky-600", tono: "text-sky-900" },
};

// Markdown mínimo para el `detail` de la tarjeta: listas con "- ", **negrita** y *cursiva*.
function Inline({ texto }) {
  return texto.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g).map((t, i) => {
    if (t.startsWith("**")) return <strong key={i} className="font-semibold">{t.slice(2, -2)}</strong>;
    if (t.startsWith("*") && t.length > 2) return <em key={i} className="text-slate-600">{t.slice(1, -1)}</em>;
    return t;
  });
}

function Markdown({ texto }) {
  const bloques = [];
  for (const linea of texto.split("\n")) {
    if (linea.startsWith("- ")) {
      const ultimo = bloques.at(-1);
      if (ultimo?.lista) ultimo.lista.push(linea.slice(2));
      else bloques.push({ lista: [linea.slice(2)] });
    } else if (linea.trim()) bloques.push({ parrafo: linea });
  }
  return (
    <div className="space-y-2 text-sm text-slate-800">
      {bloques.map((b, i) =>
        b.lista ? (
          <ul key={i} className="list-disc space-y-1.5 pl-4">
            {b.lista.map((l, j) => (
              <li key={j}><Inline texto={l} /></li>
            ))}
          </ul>
        ) : (
          <p key={i}><Inline texto={b.parrafo} /></p>
        ),
      )}
    </div>
  );
}

function TarjetaCds({ card, onAbrirAddon }) {
  const ind = INDICADOR[card.indicator] ?? INDICADOR.info;
  const Icono = ind.icono;
  return (
    <article className={`overflow-hidden rounded-md border ${ind.caja}`}>
      <div className={`h-1 ${ind.barra}`} />
      <div className="space-y-3 p-3">
        <div className="flex items-start gap-2">
          <Icono className={`mt-0.5 size-5 shrink-0 ${ind.tono}`} aria-hidden="true" />
          <div>
            <p className={`text-[11px] font-semibold uppercase tracking-wide ${ind.tono}`}>{ind.texto}</p>
            <h3 className="text-sm font-semibold leading-snug text-slate-900">{card.summary}</h3>
          </div>
        </div>
        {card.detail && <Markdown texto={card.detail} />}
        {card.suggestions?.length > 0 && (
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">Acciones sugeridas</p>
            <ul className="mt-1 space-y-1.5">
              {card.suggestions.map((s) => (
                <li
                  key={s.uuid}
                  className={`rounded border bg-white px-2.5 py-1.5 text-sm text-slate-800 ${s.isRecommended ? "border-teal-600" : "border-slate-200"}`}
                >
                  {s.label}
                  {s.isRecommended && <span className="ml-1.5 whitespace-nowrap text-[11px] font-semibold text-teal-700">· Recomendada</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
        {card.links?.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {card.links.map((l) =>
              l.type === "smart" && onAbrirAddon ? (
                <button
                  key={l.label}
                  type="button"
                  onClick={onAbrirAddon}
                  className="inline-flex items-center gap-1.5 rounded bg-teal-700 px-2.5 py-1.5 text-sm font-semibold text-white hover:bg-teal-800"
                >
                  <AppWindow className="size-4" aria-hidden="true" />
                  {l.label}
                </button>
              ) : l.type === "absolute" ? (
                <a key={l.label} href={l.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-sm font-semibold text-teal-800 hover:underline">
                  <ExternalLink className="size-4" aria-hidden="true" />
                  {l.label}
                </a>
              ) : null,
            )}
          </div>
        )}
        <p className="text-xs text-slate-500">Fuente: {card.source?.label}</p>
      </div>
    </article>
  );
}

export default function PanelCds({ id, instalacion, onAbrirAddon, onEstadoAddon }) {
  const [estado, setEstado] = useState({ id: null, peticion: null, respuesta: null, error: null });
  const [intento, setIntento] = useState(0);
  const servicio = servicioPatientView(instalacion);

  useEffect(() => {
    if (!servicio) return undefined;
    const ctrl = new AbortController();
    const peticion = peticionPatientView(id);
    setEstado({ id, peticion, respuesta: null, error: null });
    llamarPatientView(instalacion, peticion, ctrl.signal)
      .then((respuesta) => {
        setEstado({ id, peticion, respuesta, error: null });
        onEstadoAddon({ responde: true });
      })
      .catch((e) => {
        if (e.name === "AbortError") return;
        setEstado({ id, peticion, respuesta: null, error: e });
        if (e.sinRespuesta) onEstadoAddon({ responde: false, mensaje: e.message });
      });
    return () => ctrl.abort();
  }, [id, instalacion, servicio, intento, onEstadoAddon]);

  const cards = estado.id === id ? estado.respuesta?.cards : null;
  return (
    <aside className="rounded-md border border-slate-300 bg-white" aria-label="Apoyo a la decisión clínica">
      <div className="flex items-center gap-2 border-b border-slate-200 bg-slate-100 px-3 py-2">
        <Activity className="size-4 text-teal-700" aria-hidden="true" />
        <h2 className="text-sm font-semibold text-slate-900">Apoyo a la decisión</h2>
        <span className="ml-auto rounded bg-white px-1.5 py-0.5 font-mono text-[11px] text-slate-600 ring-1 ring-slate-300">CDS Hooks · patient-view</span>
      </div>
      <div className="space-y-3 p-3">
        <p className="text-xs text-slate-500">
          Add-on instalado: <span className="font-semibold text-slate-700">{nombreAddon(instalacion)}</span>
        </p>
        {!servicio ? (
          <p className="text-sm text-slate-600">El add-on instalado no ofrece ningún servicio para el hook patient-view.</p>
        ) : estado.error ? (
          <div className="rounded-md border border-red-300 bg-red-50 p-3" role="alert">
            <p className="flex items-center gap-2 text-sm font-semibold text-red-900">
              <Unplug className="size-4 shrink-0" aria-hidden="true" />
              {estado.error.sinRespuesta ? "El add-on no responde" : "El add-on ha devuelto un error"}
            </p>
            <p className="mt-1 text-sm text-red-900">{estado.error.message}</p>
            <p className="mt-1 text-sm text-red-900">La historia clínica sigue disponible; no hay apoyo a la decisión para este paciente.</p>
            <button
              type="button"
              onClick={() => setIntento((n) => n + 1)}
              className="mt-2 inline-flex items-center gap-1.5 rounded bg-white px-2.5 py-1 text-sm font-semibold text-red-800 ring-1 ring-red-300 hover:bg-red-100"
            >
              <RotateCw className="size-4" aria-hidden="true" />
              Reintentar
            </button>
          </div>
        ) : !cards ? (
          <p className="flex items-center gap-2 text-sm text-slate-600" role="status">
            <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
            Consultando el servicio CDS…
          </p>
        ) : cards.length === 0 ? (
          <p className="text-sm text-slate-600">El servicio no devuelve recomendaciones para este paciente.</p>
        ) : (
          cards.map((c) => <TarjetaCds key={c.uuid} card={c} onAbrirAddon={instalacion.app ? onAbrirAddon : null} />)
        )}
        {servicio && estado.peticion && estado.id === id && (
          <details className="rounded border border-slate-200 text-xs">
            <summary className="cursor-pointer px-2.5 py-1.5 font-semibold text-slate-700">Ver el intercambio CDS Hooks (JSON)</summary>
            <div className="space-y-2 border-t border-slate-200 p-2.5">
              <p className="break-all font-mono text-slate-600">
                POST {instalacion.url}/cds-services/{servicio.id}
              </p>
              <pre className="max-h-40 overflow-auto rounded bg-slate-900 p-2 text-[11px] leading-relaxed text-slate-100">{JSON.stringify(estado.peticion, null, 2)}</pre>
              {estado.respuesta && (
                <pre className="max-h-64 overflow-auto rounded bg-slate-900 p-2 text-[11px] leading-relaxed text-slate-100">{JSON.stringify(estado.respuesta, null, 2)}</pre>
              )}
            </div>
          </details>
        )}
      </div>
    </aside>
  );
}
