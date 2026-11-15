import { useState } from "react";
import { AppWindow, CircleCheck, LoaderCircle, PanelRight, Plug, RotateCw, Trash2, TriangleAlert, Unplug } from "lucide-react";
import { descubrir, instalar, nombreAddon, URL_POR_DEFECTO } from "../integracion.js";
import { fechaHora } from "../format.js";

// Configuración → Integraciones: instalar o desinstalar un add-on de apoyo a la decisión por su URL.
// Al instalar, la estación consulta el discovery de CDS Hooks y registra los servicios que encuentra.

function Servicios({ servicios }) {
  return (
    <div className="overflow-x-auto rounded border border-slate-200">
      <table className="w-full border-collapse text-left text-sm">
        <thead>
          <tr className="bg-slate-100 text-[11px] font-semibold uppercase tracking-wide text-slate-600">
            <th scope="col" className="px-3 py-2">Servicio</th>
            <th scope="col" className="px-3 py-2">Identificador</th>
            <th scope="col" className="px-3 py-2">Hook</th>
            <th scope="col" className="px-3 py-2">Descripción</th>
          </tr>
        </thead>
        <tbody>
          {servicios.map((s) => (
            <tr key={s.id} className="border-t border-slate-200 align-top">
              <td className="whitespace-nowrap px-3 py-2 font-semibold text-slate-900">{s.title ?? "—"}</td>
              <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-slate-700">{s.id}</td>
              <td className="whitespace-nowrap px-3 py-2">
                <span className="rounded bg-teal-50 px-1.5 py-0.5 font-mono text-xs text-teal-900 ring-1 ring-teal-200">{s.hook}</span>
              </td>
              <td className="px-3 py-2 text-slate-700">{s.description ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Integraciones({ instalacion, estadoAddon, onInstalada, onDesinstalar, onEstadoAddon }) {
  const [url, setUrl] = useState(URL_POR_DEFECTO);
  const [trabajando, setTrabajando] = useState(false);
  const [error, setError] = useState(null);
  const [comprobacion, setComprobacion] = useState(null); // resultado de "Volver a comprobar"

  async function enviar(e) {
    e.preventDefault();
    setTrabajando(true);
    setError(null);
    try {
      onInstalada(await instalar(url));
    } catch (err) {
      setError(err.message);
    } finally {
      setTrabajando(false);
    }
  }

  async function comprobar() {
    setTrabajando(true);
    setComprobacion(null);
    try {
      const { servicios } = await descubrir(instalacion.url);
      setComprobacion({ ok: true, texto: `El add-on responde: ${servicios.length} ${servicios.length === 1 ? "servicio" : "servicios"} en el discovery.` });
      onEstadoAddon({ responde: true });
    } catch (err) {
      setComprobacion({ ok: false, texto: err.message });
      if (err.sinRespuesta) onEstadoAddon({ responde: false, mensaje: err.message });
    } finally {
      setTrabajando(false);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-semibold text-slate-900">Integraciones</h2>
        <p className="mt-1 max-w-3xl text-sm text-slate-600">
          Add-ons de apoyo a la decisión clínica que se conectan a esta estación por estándares: HL7 CDS Hooks para las tarjetas y el servidor FHIR
          de la estación para leer los datos de los pacientes. La estación funciona igual sin ninguno instalado.
        </p>
      </div>

      {!instalacion ? (
        <section className="rounded-md border border-slate-300 bg-white">
          <div className="flex items-center gap-2 border-b border-slate-200 bg-slate-100 px-4 py-2.5">
            <Plug className="size-4 text-teal-700" aria-hidden="true" />
            <h2 className="text-sm font-semibold text-slate-900">Instalar un add-on</h2>
            <span className="ml-auto rounded-full bg-slate-200 px-2 py-0.5 text-xs font-semibold text-slate-700">Ningún add-on instalado</span>
          </div>
          <form onSubmit={enviar} className="space-y-3 p-4">
            <div>
              <label htmlFor="url-addon" className="block text-sm font-semibold text-slate-900">
                URL del add-on
              </label>
              <div className="mt-1 flex flex-wrap gap-2">
                <input
                  id="url-addon"
                  type="text"
                  inputMode="url"
                  autoComplete="off"
                  spellCheck={false}
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder={URL_POR_DEFECTO}
                  aria-describedby="url-ayuda"
                  className="h-9 min-w-64 flex-1 rounded border border-slate-400 bg-white px-2.5 font-mono text-sm text-slate-900"
                />
                <button
                  type="submit"
                  disabled={trabajando}
                  className="inline-flex h-9 items-center gap-2 rounded bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800 disabled:opacity-60"
                >
                  {trabajando ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : <Plug className="size-4" aria-hidden="true" />}
                  Instalar
                </button>
              </div>
              <p id="url-ayuda" className="mt-1.5 text-sm text-slate-600">
                Al instalar, la estación consulta <span className="font-mono text-xs">GET {"{URL}"}/cds-services</span> (discovery) y registra los servicios
                que encuentra. No se envía ningún dato de pacientes: el add-on los leerá del servidor FHIR de la estación cuando los necesite.
              </p>
            </div>
            {error && (
              <p className="flex items-start gap-2 rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-900" role="alert">
                <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                <span>No se ha instalado nada. {error}</span>
              </p>
            )}
          </form>
        </section>
      ) : (
        <section className="rounded-md border border-slate-300 bg-white">
          <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 bg-slate-100 px-4 py-2.5">
            <Plug className="size-4 text-teal-700" aria-hidden="true" />
            <h2 className="text-sm font-semibold text-slate-900">{nombreAddon(instalacion)}</h2>
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-900 ring-1 ring-inset ring-emerald-300">
              <CircleCheck className="size-3.5" aria-hidden="true" />
              Instalado
            </span>
            {estadoAddon?.responde === false && (
              <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-900 ring-1 ring-inset ring-red-300">
                <Unplug className="size-3.5" aria-hidden="true" />
                No responde
              </span>
            )}
          </div>
          <div className="space-y-4 p-4">
            <dl className="grid gap-x-8 gap-y-2 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-[11px] uppercase tracking-wide text-slate-500">URL del add-on</dt>
                <dd className="break-all font-mono text-slate-900">{instalacion.url}</dd>
              </div>
              <div>
                <dt className="text-[11px] uppercase tracking-wide text-slate-500">Instalado el</dt>
                <dd className="text-slate-900">{fechaHora(instalacion.instaladoEn)}</dd>
              </div>
            </dl>

            <div>
              <h3 className="mb-1.5 text-sm font-semibold text-slate-900">
                Servicios encontrados en el discovery ({instalacion.servicios.length})
              </h3>
              <Servicios servicios={instalacion.servicios} />
            </div>

            <div>
              <h3 className="mb-1.5 text-sm font-semibold text-slate-900">Qué añade a la estación</h3>
              <ul className="space-y-1.5 text-sm text-slate-700">
                <li className="flex items-start gap-2">
                  <PanelRight className="mt-0.5 size-4 shrink-0 text-teal-700" aria-hidden="true" />
                  <span>
                    Panel «Apoyo a la decisión» al abrir un paciente: la estación lanza el hook <span className="font-mono text-xs">patient-view</span> con
                    la dirección de su servidor FHIR (<span className="font-mono text-xs">fhirServer</span>) y muestra la tarjeta del add-on, que enlaza con
                    la ficha del paciente.
                  </span>
                </li>
                {instalacion.app ? (
                  <li className="flex items-start gap-2">
                    <AppWindow className="mt-0.5 size-4 shrink-0 text-teal-700" aria-hidden="true" />
                    <span>
                      Botón «{instalacion.app.titulo}» en la barra de herramientas: abre la página principal del add-on (
                      <span className="break-all font-mono text-xs">{instalacion.app.launchUrl}</span>) en una ventana sobre la estación, con las alertas, la
                      lista «Hoy» y las prioridades del cupo activo. La estación le pasa su servidor FHIR (<span className="font-mono text-xs">iss</span>) y
                      el profesional y el paciente como contexto (lanzamiento SMART on FHIR simulado).
                    </span>
                  </li>
                ) : (
                  <li className="flex items-start gap-2 text-slate-500">
                    <AppWindow className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                    <span>El add-on no anuncia ninguna interfaz propia: no se añade botón a la barra de herramientas.</span>
                  </li>
                )}
              </ul>
            </div>

            <details className="rounded border border-slate-200 text-xs">
              <summary className="cursor-pointer px-2.5 py-1.5 font-semibold text-slate-700">Ver la respuesta del discovery (JSON)</summary>
              <div className="space-y-2 border-t border-slate-200 p-2.5">
                <p className="break-all font-mono text-slate-600">GET {instalacion.url}/cds-services</p>
                <pre className="max-h-72 overflow-auto rounded bg-slate-900 p-2 text-[11px] leading-relaxed text-slate-100">
                  {JSON.stringify(instalacion.discovery ?? { services: instalacion.servicios }, null, 2)}
                </pre>
              </div>
            </details>

            {comprobacion && (
              <p
                className={`rounded border px-3 py-2 text-sm ${comprobacion.ok ? "border-emerald-300 bg-emerald-50 text-emerald-900" : "border-red-300 bg-red-50 text-red-900"}`}
                role={comprobacion.ok ? "status" : "alert"}
              >
                {comprobacion.texto}
              </p>
            )}

            <div className="flex flex-wrap items-center gap-2 border-t border-slate-200 pt-3">
              <button
                type="button"
                onClick={comprobar}
                disabled={trabajando}
                className="inline-flex h-9 items-center gap-2 rounded bg-white px-3 text-sm font-semibold text-slate-800 ring-1 ring-inset ring-slate-400 hover:bg-slate-50 disabled:opacity-60"
              >
                {trabajando ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : <RotateCw className="size-4" aria-hidden="true" />}
                Volver a comprobar
              </button>
              <button
                type="button"
                onClick={onDesinstalar}
                className="inline-flex h-9 items-center gap-2 rounded bg-white px-3 text-sm font-semibold text-red-800 ring-1 ring-inset ring-red-400 hover:bg-red-50"
              >
                <Trash2 className="size-4" aria-hidden="true" />
                Desinstalar
              </button>
              <span className="text-sm text-slate-500">Al desinstalar desaparecen el panel y el botón; la historia clínica no cambia.</span>
            </div>
          </div>
        </section>
      )}

      <p className="text-xs text-slate-500">
        El estado de instalación se guarda en este navegador y se mantiene al recargar la página.
      </p>
    </div>
  );
}
