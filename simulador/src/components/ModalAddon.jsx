import { useEffect, useMemo, useRef, useState } from "react";
import { LoaderCircle, RotateCw, Unplug, X } from "lucide-react";
import { ESTACION, interfazResponde, nombreAddon, PROFESIONAL, urlLanzamiento } from "../integracion.js";

// Ventana modal sobre la estación con la interfaz completa del add-on dentro de un iframe.
// La estación le pasa su servidor FHIR (`iss`), el paciente abierto y el profesional (lanzamiento SMART on FHIR
// simulado). `vista`: "cupo" abre la página principal del add-on; "ficha", la ficha del paciente abierto.
export default function ModalAddon({ instalacion, paciente, vista = "cupo", onCerrar }) {
  const [estado, setEstado] = useState("comprobando"); // comprobando | ok | sin_respuesta
  const [intento, setIntento] = useState(0);
  const botonCerrar = useRef(null);
  const nombre = nombreAddon(instalacion);
  const pacienteId = paciente?.id ?? null;
  const src = useMemo(() => urlLanzamiento(instalacion, pacienteId, vista), [instalacion, pacienteId, vista]);

  useEffect(() => {
    let vivo = true;
    setEstado("comprobando");
    interfazResponde(instalacion).then((ok) => vivo && setEstado(ok ? "ok" : "sin_respuesta"));
    return () => {
      vivo = false;
    };
  }, [instalacion, intento]);

  // Esc cierra; mientras está abierta, la estación de debajo no se desplaza.
  useEffect(() => {
    const previo = document.activeElement;
    const tecla = (e) => e.key === "Escape" && onCerrar();
    window.addEventListener("keydown", tecla);
    document.body.style.overflow = "hidden";
    botonCerrar.current?.focus();
    return () => {
      window.removeEventListener("keydown", tecla);
      document.body.style.overflow = "";
      previo?.focus?.();
    };
  }, [onCerrar]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-3 sm:p-5" onMouseDown={(e) => e.target === e.currentTarget && onCerrar()}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-addon-titulo"
        className="flex h-full w-full max-w-[1500px] flex-col overflow-hidden rounded-lg bg-white shadow-2xl ring-1 ring-slate-900/20"
      >
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-slate-300 bg-slate-800 px-4 py-2 text-white">
          <h2 id="modal-addon-titulo" className="text-sm font-semibold">
            {nombre} <span className="font-normal text-slate-300">· add-on abierto desde la {ESTACION.toLowerCase()}</span>
          </h2>
          <dl className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-200">
            <div className="flex gap-1">
              <dt className="text-slate-400">Paciente:</dt>
              <dd className="font-semibold">{paciente ? `${paciente.nombre} (${paciente.id})` : "ninguno abierto"}</dd>
            </div>
            <div className="flex gap-1">
              <dt className="text-slate-400">Profesional:</dt>
              <dd className="font-semibold">{PROFESIONAL.nombre}</dd>
            </div>
          </dl>
          <span className="rounded bg-slate-700 px-1.5 py-0.5 text-[11px] text-slate-200">Lanzamiento SMART on FHIR simulado</span>
          <button
            ref={botonCerrar}
            type="button"
            onClick={onCerrar}
            className="ml-auto inline-flex h-8 items-center gap-1.5 rounded bg-white px-3 text-sm font-semibold text-slate-900 hover:bg-slate-100"
          >
            <X className="size-4" aria-hidden="true" />
            Cerrar y volver a la estación
          </button>
        </div>

        <div className="relative min-h-0 flex-1 bg-slate-100">
          {estado === "comprobando" && (
            <p className="flex h-full items-center justify-center gap-2 text-sm text-slate-600" role="status">
              <LoaderCircle className="size-5 animate-spin text-teal-700" aria-hidden="true" />
              Abriendo {nombre}…
            </p>
          )}
          {estado === "sin_respuesta" && (
            <div className="flex h-full items-center justify-center p-6">
              <div className="max-w-xl rounded-md border border-red-300 bg-red-50 p-5 text-center" role="alert">
                <Unplug className="mx-auto size-8 text-red-700" aria-hidden="true" />
                <p className="mt-2 text-base font-semibold text-red-900">La interfaz de {nombre} no responde</p>
                <p className="mt-1 text-sm text-red-900">
                  No hay respuesta en <span className="break-all font-mono text-xs">{instalacion.app.launchUrl}</span>. Compruebe que el add-on está
                  arrancado (<span className="font-mono text-xs">start_addon</span>) y vuelva a intentarlo. La estación clínica sigue funcionando.
                </p>
                <div className="mt-3 flex justify-center gap-2">
                  <button
                    type="button"
                    onClick={() => setIntento((n) => n + 1)}
                    className="inline-flex items-center gap-1.5 rounded bg-white px-3 py-1.5 text-sm font-semibold text-red-800 ring-1 ring-red-300 hover:bg-red-100"
                  >
                    <RotateCw className="size-4" aria-hidden="true" />
                    Reintentar
                  </button>
                  <button type="button" onClick={onCerrar} className="rounded bg-white px-3 py-1.5 text-sm font-semibold text-slate-800 ring-1 ring-slate-300 hover:bg-slate-50">
                    Volver a la estación
                  </button>
                </div>
              </div>
            </div>
          )}
          {estado === "ok" && <iframe key={src} src={src} title={`Interfaz de ${nombre}`} className="size-full border-0 bg-white" />}
        </div>
      </div>
    </div>
  );
}
