import { useState } from "react";
import { FlaskConical, LoaderCircle, UserPlus, X } from "lucide-react";
import { altaPaciente, ORIGENES, PRUEBAS, registrarAnalitica } from "../historia.js";
import { fecha } from "../format.js";

// Escritura en la historia de la estación: registrar una analítica y dar de alta un paciente. Lo escrito vive
// en la memoria del servidor FHIR de la estación (se pierde al reiniciarla); el add-on se entera por la
// suscripción FHIR (analíticas) o en la siguiente lectura del cupo (pacientes nuevos).

function Ventana({ titulo, icono: Icono, onCerrar, children }) {
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/50 px-4 py-10" role="dialog" aria-modal="true" aria-label={titulo}>
      <div className="w-full max-w-md rounded-md bg-white shadow-xl">
        <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-3">
          <Icono className="size-5 text-teal-700" aria-hidden="true" />
          <h2 className="flex-1 text-base font-semibold text-slate-900">{titulo}</h2>
          <button type="button" onClick={onCerrar} className="rounded p-1 text-slate-500 hover:bg-slate-100" aria-label="Cerrar">
            <X className="size-5" aria-hidden="true" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

const campo = "mt-1 h-9 w-full rounded border border-slate-300 bg-white px-2 text-sm text-slate-900";
const etiqueta = "block text-sm font-medium text-slate-800";

function Pie({ trabajando, error, onCerrar, texto }) {
  return (
    <>
      {error && (
        <p className="mx-4 mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900" role="alert">
          {error}
        </p>
      )}
      <div className="flex justify-end gap-2 border-t border-slate-200 px-4 py-3">
        <button type="button" onClick={onCerrar} className="rounded px-3 py-1.5 text-sm font-semibold text-slate-700 hover:bg-slate-100">
          Cancelar
        </button>
        <button
          type="submit"
          disabled={trabajando}
          className="inline-flex items-center gap-2 rounded bg-teal-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
        >
          {trabajando && <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />}
          {texto}
        </button>
      </div>
    </>
  );
}

export function RegistrarAnalitica({ paciente, hoy, origenHabitual, onCerrar, onRegistrada }) {
  const [loinc, setLoinc] = useState(PRUEBAS[0].loinc);
  const [valor, setValor] = useState("");
  const [origen, setOrigen] = useState(origenHabitual && ORIGENES.includes(origenHabitual) ? origenHabitual : ORIGENES[0]);
  const [trabajando, setTrabajando] = useState(false);
  const [error, setError] = useState(null);
  const prueba = PRUEBAS.find((p) => p.loinc === loinc);

  async function enviar(e) {
    e.preventDefault();
    const numero = Number(String(valor).replace(",", "."));
    if (!String(valor).trim() || !Number.isFinite(numero) || numero < 0) {
      setError("Escriba un valor numérico positivo.");
      return;
    }
    setTrabajando(true);
    setError(null);
    try {
      const obs = await registrarAnalitica(paciente.id, { prueba, valor: numero, origen });
      onRegistrada(obs);
    } catch (err) {
      setError(err.message);
      setTrabajando(false);
    }
  }

  return (
    <Ventana titulo="Registrar analítica" icono={FlaskConical} onCerrar={onCerrar}>
      <form onSubmit={enviar}>
        <div className="space-y-3 px-4 py-4">
          <p className="text-sm text-slate-600">
            {paciente.nombre} · Historia n.º {paciente.id} · fecha <strong className="font-semibold text-slate-900">{fecha(hoy)}</strong> (hoy en la simulación)
          </p>
          <label className={etiqueta}>
            Prueba
            <select value={loinc} onChange={(e) => setLoinc(e.target.value)} className={campo}>
              {PRUEBAS.map((p) => (
                <option key={p.loinc} value={p.loinc}>
                  {p.nombre} (LOINC {p.loinc})
                </option>
              ))}
            </select>
          </label>
          <div className="grid grid-cols-[1fr_7rem] gap-3">
            <label className={etiqueta}>
              Valor
              <input autoFocus inputMode="decimal" value={valor} onChange={(e) => setValor(e.target.value)} className={campo} placeholder="p. ej. 450" />
            </label>
            <label className={etiqueta}>
              Unidad
              <input value={prueba.unidad} readOnly className={`${campo} bg-slate-50 text-slate-600`} />
            </label>
          </div>
          <label className={etiqueta}>
            Sistema de origen
            <select value={origen} onChange={(e) => setOrigen(e.target.value)} className={campo}>
              {ORIGENES.map((o) => (
                <option key={o}>{o}</option>
              ))}
            </select>
          </label>
        </div>
        <Pie trabajando={trabajando} error={error} onCerrar={onCerrar} texto="Registrar" />
      </form>
    </Ventana>
  );
}

export function AltaPaciente({ hoy, onCerrar, onAlta }) {
  const [datos, setDatos] = useState({ nombre: "", apellidos: "", sexo: "D", nacimiento: "" });
  const [trabajando, setTrabajando] = useState(false);
  const [error, setError] = useState(null);
  const cambiar = (k) => (e) => setDatos((d) => ({ ...d, [k]: e.target.value }));

  async function enviar(e) {
    e.preventDefault();
    if (!datos.nombre.trim() || !datos.apellidos.trim() || !datos.nacimiento) {
      setError("Rellene el nombre, los apellidos y la fecha de nacimiento.");
      return;
    }
    setTrabajando(true);
    setError(null);
    try {
      onAlta(await altaPaciente(datos));
    } catch (err) {
      setError(err.message);
      setTrabajando(false);
    }
  }

  return (
    <Ventana titulo="Alta de paciente en el cupo" icono={UserPlus} onCerrar={onCerrar}>
      <form onSubmit={enviar}>
        <div className="space-y-3 px-4 py-4">
          <div className="grid grid-cols-2 gap-3">
            <label className={etiqueta}>
              Nombre
              <input autoFocus value={datos.nombre} onChange={cambiar("nombre")} className={campo} />
            </label>
            <label className={etiqueta}>
              Apellidos
              <input value={datos.apellidos} onChange={cambiar("apellidos")} className={campo} />
            </label>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <label className={etiqueta}>
              Sexo
              <select value={datos.sexo} onChange={cambiar("sexo")} className={campo}>
                <option value="D">Mujer</option>
                <option value="H">Hombre</option>
              </select>
            </label>
            <label className={etiqueta}>
              Fecha de nacimiento
              <input type="date" max={hoy} value={datos.nacimiento} onChange={cambiar("nacimiento")} className={campo} />
            </label>
          </div>
          <p className="text-xs text-slate-500">El add-on lo incluirá en la siguiente lectura del cupo (cambia el recurso Group de la estación).</p>
        </div>
        <Pie trabajando={trabajando} error={error} onCerrar={onCerrar} texto="Dar de alta" />
      </form>
    </Ventana>
  );
}
