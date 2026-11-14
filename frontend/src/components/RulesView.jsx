import { useEffect, useMemo, useState } from "react";
import { CircleCheck, Info, LoaderCircle, RotateCcw, Save, ShieldCheck, TriangleAlert } from "lucide-react";
import { api } from "../api.js";
import { GRUPO_CORTO, num } from "../format.js";
import { Cargando, ErrorPanel } from "./ui.jsx";

const aNumero = (texto) => Number(String(texto).replace(",", "."));

function Campo({ e, valor, error, onChange }) {
  const cambiado = e.tipus === "boolea" ? valor !== e.valor : aNumero(valor) !== e.valor;
  const id = `campo-${e.cami}`;
  const marco = error ? "border-red-400 bg-red-50" : cambiado ? "border-clinic-500 bg-clinic-50" : "border-line bg-white";

  if (e.tipus === "boolea") {
    return (
      <div className={`flex items-center justify-between gap-3 rounded-md border px-3 py-2.5 ${marco}`}>
        <label htmlFor={id} className="text-sm text-ink">
          {e.etiqueta}
        </label>
        <button
          id={id}
          type="button"
          role="switch"
          aria-checked={valor}
          onClick={() => onChange(!valor)}
          className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${valor ? "bg-clinic-600" : "bg-slate-300"}`}
        >
          <span className={`absolute top-0.5 size-5 rounded-full bg-white shadow transition-all ${valor ? "left-5.5" : "left-0.5"}`} />
          <span className="sr-only">{valor ? "Activado" : "Desactivado"}</span>
        </button>
      </div>
    );
  }
  return (
    <div className={`rounded-md border px-3 py-2.5 ${marco}`}>
      <label htmlFor={id} className="block text-sm text-ink">
        {e.etiqueta}
      </label>
      <div className="mt-1.5 flex items-center gap-2">
        <input
          id={id}
          type="number"
          inputMode="decimal"
          min={e.minim}
          max={e.maxim}
          step={e.pas}
          value={valor}
          onChange={(ev) => onChange(ev.target.value)}
          aria-invalid={Boolean(error)}
          aria-describedby={`${id}-ayuda`}
          className="tabular h-9 w-24 rounded-md border border-line bg-white px-2 text-right text-sm font-semibold text-ink"
        />
        <span className="text-xs text-muted">{e.unitat}</span>
        {cambiado && !error && <span className="ml-auto text-xs text-clinic-700">antes: {num(e.valor, Number.isInteger(e.valor) ? 0 : 1)}</span>}
      </div>
      <p id={`${id}-ayuda`} className={`mt-1 text-xs ${error ? "font-medium text-red-800" : "text-muted"}`}>
        {error || e.ajuda || `Entre ${num(e.minim, 1).replace(",0", "")} y ${num(e.maxim)} ${e.unitat}`}
      </p>
    </div>
  );
}

function Efecto({ etiqueta, ahora, antes }) {
  const delta = antes == null ? 0 : ahora - antes;
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line py-2 last:border-b-0">
      <dt className="text-sm text-ink">{etiqueta}</dt>
      <dd className="tabular text-right">
        <span className="text-xl font-semibold text-ink">{num(ahora)}</span>
        {delta !== 0 && (
          <span className="ml-2 text-xs font-semibold text-clinic-700">
            {delta > 0 ? "+" : "−"}
            {Math.abs(delta)} (antes {antes})
          </span>
        )}
      </dd>
    </div>
  );
}

export default function RulesView({ kpis, recalculando, onSaved }) {
  const [estado, setEstado] = useState({ data: null, error: null });
  const [valores, setValores] = useState({});
  const [errores, setErrores] = useState({});
  const [guardando, setGuardando] = useState(false);
  const [resultado, setResultado] = useState(null); // {tipo: "ok"|"error", texto}
  const [antes, setAntes] = useState(null); // indicadores del cupo antes del último guardado
  const [intento, setIntento] = useState(0);

  const cargar = (data) => {
    setEstado({ data, error: null });
    setValores(Object.fromEntries(data.editables.map((e) => [e.cami, e.tipus === "boolea" ? e.valor : String(e.valor)])));
    setErrores({});
  };

  useEffect(() => {
    const ctrl = new AbortController();
    api
      .rules(ctrl.signal)
      .then(cargar)
      .catch((e) => e.name !== "AbortError" && setEstado({ data: null, error: e.message }));
    return () => ctrl.abort();
  }, [intento]);

  const editables = estado.data?.editables ?? [];
  const grupos = useMemo(() => {
    const g = new Map();
    editables.forEach((e) => g.set(e.grup, [...(g.get(e.grup) ?? []), e]));
    return [...g];
  }, [editables]);

  const cambios = useMemo(() => {
    const c = {};
    for (const e of editables) {
      const v = e.tipus === "boolea" ? valores[e.cami] : aNumero(valores[e.cami]);
      if (v !== e.valor) c[e.cami] = v;
    }
    return c;
  }, [editables, valores]);
  const nCambios = Object.keys(cambios).length;

  if (estado.error) return <ErrorPanel mensaje={estado.error} onRetry={() => setIntento((n) => n + 1)} />;
  if (!estado.data) return <Cargando texto="Cargando los parámetros del protocolo…" />;

  async function guardar(ev) {
    ev.preventDefault();
    const invalidos = Object.fromEntries(
      Object.entries(cambios).filter(([, v]) => typeof v === "number" && Number.isNaN(v)).map(([k]) => [k, "Debe ser un número"]),
    );
    if (Object.keys(invalidos).length) {
      setErrores(invalidos);
      setResultado({ tipo: "error", texto: "Revisa los campos marcados: no se ha guardado nada." });
      return;
    }
    setGuardando(true);
    setResultado(null);
    try {
      const data = await api.saveRules(cambios);
      setAntes(kpis);
      cargar(data);
      const n = Object.keys(data.canviats).length;
      setResultado({
        tipo: "ok",
        texto: `${n} ${n === 1 ? "parámetro guardado" : "parámetros guardados"} en rules.yaml. Copia de seguridad: config/backups/${data.backup}. Cupo recalculado.`,
      });
      onSaved();
    } catch (e) {
      setErrores(e.errors ?? {});
      setResultado({ tipo: "error", texto: `${e.message}${e.errors?.motor ? ` (${e.errors.motor})` : ""}` });
    } finally {
      setGuardando(false);
    }
  }

  return (
    <form onSubmit={guardar} className="grid gap-4 xl:grid-cols-3" noValidate>
      <div className="space-y-4 xl:col-span-2">
        <div className="rounded-lg border border-line bg-white p-4 shadow-xs">
          <h1 className="text-xl font-semibold text-ink">Parámetros del protocolo</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted">
            Umbrales que usa el motor de reglas, leídos de <code className="rounded bg-clinic-50 px-1 text-ink">config/rules.yaml</code>. Al guardar se
            validan, se hace una copia de seguridad del fichero y el cupo se recalcula al instante, sin tocar código.
          </p>
          <p className="mt-3 flex items-start gap-2 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900 ring-1 ring-inset ring-amber-200">
            <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            Todos los valores están pendientes de validación por el equipo médico.
          </p>
        </div>

        {grupos.map(([grupo, campos]) => (
          <fieldset key={grupo} className="rounded-lg border border-line bg-white shadow-xs">
            <legend className="sr-only">{grupo}</legend>
            <h2 className="border-b border-line px-4 py-2.5 text-sm font-semibold text-ink" aria-hidden="true">
              {grupo}
            </h2>
            <div className="grid gap-3 p-4 sm:grid-cols-2">
              {campos.map((e) => (
                <Campo
                  key={e.cami}
                  e={e}
                  valor={valores[e.cami]}
                  error={errores[e.cami]}
                  onChange={(v) => {
                    setValores((s) => ({ ...s, [e.cami]: v }));
                    setErrores((s) => ({ ...s, [e.cami]: undefined }));
                  }}
                />
              ))}
            </div>
          </fieldset>
        ))}
      </div>

      <aside className="space-y-4 xl:sticky xl:top-36 xl:self-start">
        <div className="rounded-lg border border-line bg-white p-4 shadow-xs">
          <h2 className="text-sm font-semibold text-ink">Guardar cambios</h2>
          <p className="mt-1 text-sm text-muted" role="status">
            {nCambios === 0 ? "Sin cambios pendientes." : `${nCambios} ${nCambios === 1 ? "parámetro modificado" : "parámetros modificados"} sin guardar.`}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="submit"
              disabled={nCambios === 0 || guardando}
              className="inline-flex items-center gap-2 rounded-md bg-clinic-600 px-4 py-2 text-sm font-semibold text-white hover:bg-clinic-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {guardando ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : <Save className="size-4" aria-hidden="true" />}
              Guardar y recalcular
            </button>
            <button
              type="button"
              disabled={nCambios === 0 || guardando}
              onClick={() => {
                cargar(estado.data);
                setResultado(null);
              }}
              className="inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-semibold text-clinic-700 ring-1 ring-inset ring-line hover:bg-clinic-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <RotateCcw className="size-4" aria-hidden="true" />
              Descartar
            </button>
          </div>
          {resultado && (
            <p
              role={resultado.tipo === "error" ? "alert" : "status"}
              className={`mt-3 flex items-start gap-2 rounded-md px-3 py-2 text-sm ring-1 ring-inset ${
                resultado.tipo === "ok" ? "bg-emerald-50 text-emerald-900 ring-emerald-200" : "bg-red-50 text-red-900 ring-red-200"
              }`}
            >
              {resultado.tipo === "ok" ? (
                <CircleCheck className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              ) : (
                <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              )}
              <span className="break-words [overflow-wrap:anywhere]">{resultado.texto}</span>
            </p>
          )}
          <p className="mt-3 flex items-start gap-2 text-xs text-muted">
            <ShieldCheck className="mt-0.5 size-4 shrink-0 text-clinic-600" aria-hidden="true" />
            {estado.data.backups} {estado.data.backups === 1 ? "copia de seguridad guardada" : "copias de seguridad guardadas"} en config/backups.
          </p>
        </div>

        {kpis && (
          <div className={`rounded-lg border border-line bg-white p-4 shadow-xs transition-opacity ${recalculando ? "opacity-60" : ""}`}>
            <h2 className="text-sm font-semibold text-ink">Efecto en el cupo</h2>
            <p className="mt-0.5 text-xs text-muted">Con los parámetros guardados{antes ? "; entre paréntesis, antes del último cambio." : "."}</p>
            <dl className="mt-2">
              {Object.keys(kpis.categories).map((c) => (
                <Efecto key={c} etiqueta={`Riesgo CV ${c}`} ahora={kpis.categories[c]} antes={antes?.categories[c]} />
              ))}
              {Object.keys(kpis.grups).map((g) => (
                <Efecto key={g} etiqueta={`Lista: ${GRUPO_CORTO[g]}`} ahora={kpis.grups[g]} antes={antes?.grups[g]} />
              ))}
              <Efecto etiqueta="Alertas activas" ahora={kpis.alertes} antes={antes?.alertes} />
              <Efecto etiqueta="UACR pendiente" ahora={kpis.uacr_pendent} antes={antes?.uacr_pendent} />
              <Efecto etiqueta="Riesgo CV alto o muy alto" ahora={kpis.risc_cv_alt} antes={antes?.risc_cv_alt} />
            </dl>
            <a href="#/" className="mt-3 inline-block text-sm font-semibold text-clinic-700 hover:underline">
              Ver el cupo recalculado
            </a>
          </div>
        )}
        <p className="flex items-start gap-2 px-1 text-xs text-muted">
          <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          El resto de reglas (fármacos, clases de evidencia, objetivos de tratamiento) se edita directamente en config/rules.yaml.
        </p>
      </aside>
    </form>
  );
}
