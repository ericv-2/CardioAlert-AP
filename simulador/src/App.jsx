import { useCallback, useEffect, useState } from "react";
import { ArrowRight, CalendarDays, HeartPulse, PlugZap, Settings, Stethoscope, Unplug, UserRound, X } from "lucide-react";
import { cargarAgenda } from "./historia.js";
import { descubrir, desinstalar, leerInstalacion, nombreAddon, PROFESIONAL } from "./integracion.js";
import { fecha } from "./format.js";
import Agenda from "./components/Agenda.jsx";
import Historia from "./components/Historia.jsx";
import Integraciones from "./components/Integraciones.jsx";
import ModalAddon from "./components/ModalAddon.jsx";
import PanelCds from "./components/PanelCds.jsx";

// Estación clínica SIMULADA: historia clínica genérica de atención primaria de una comunidad.
// No reproduce ningún producto real. Por defecto NO tiene ningún add-on: se instala en
// Configuración → Integraciones, y solo entonces aparecen el panel lateral y el botón del add-on.

function parseHash() {
  const [seg, id] = window.location.hash.replace(/^#\/?/, "").split("/");
  if (seg === "paciente" && id) return { vista: "historia", id: decodeURIComponent(id) };
  if (seg === "configuracion") return { vista: "integraciones" };
  return { vista: "historia", id: null };
}

function Pestana({ href, activa, icono: Icono, children }) {
  return (
    <a
      href={href}
      aria-current={activa ? "page" : undefined}
      className={`inline-flex h-9 items-center gap-1.5 rounded px-3 text-sm font-semibold ${activa ? "bg-white text-slate-900" : "text-slate-100 hover:bg-white/10"}`}
    >
      <Icono className="size-4" aria-hidden="true" />
      {children}
    </a>
  );
}

export default function App() {
  const [ruta, setRuta] = useState(parseHash);
  const [agenda, setAgenda] = useState({ data: null, error: null });
  const [instalacion, setInstalacion] = useState(leerInstalacion); // null = ningún add-on instalado
  const [estadoAddon, setEstadoAddon] = useState(null); // { responde } según el último contacto con el add-on
  const [avisoOculto, setAvisoOculto] = useState(false);
  const [modal, setModal] = useState(false);

  useEffect(() => {
    const onHash = () => {
      setRuta(parseHash());
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    cargarAgenda(ctrl.signal)
      .then((data) => setAgenda({ data, error: null }))
      .catch((e) => e.name !== "AbortError" && setAgenda({ data: null, error: e.message }));
    return () => ctrl.abort();
  }, []);

  const informarEstado = useCallback((estado) => {
    setEstadoAddon(estado);
    if (estado?.responde) setAvisoOculto(false);
  }, []);

  // Con un add-on instalado, al entrar en la estación se comprueba que sigue respondiendo.
  const comprobarAddon = useCallback(
    (signal) => {
      if (!instalacion) return;
      descubrir(instalacion.url, signal)
        .then(() => informarEstado({ responde: true }))
        .catch((e) => e.name !== "AbortError" && informarEstado({ responde: false, mensaje: e.message }));
    },
    [instalacion, informarEstado],
  );
  useEffect(() => {
    const ctrl = new AbortController();
    setEstadoAddon(null);
    setAvisoOculto(false);
    comprobarAddon(ctrl.signal);
    return () => ctrl.abort();
  }, [comprobarAddon]);

  const quitarAddon = useCallback(() => {
    desinstalar();
    setInstalacion(null);
    setModal(false);
  }, []);
  const cerrarModal = useCallback(() => setModal(false), []);
  const abrirModal = useCallback(() => setModal(true), []);

  const abierto = ruta.vista === "historia" ? ruta.id : null;
  const pacienteAbierto = abierto ? (agenda.data?.pacientes.find((p) => p.id === abierto) ?? { id: abierto, nombre: abierto }) : null;
  const addon = instalacion ? nombreAddon(instalacion) : null;
  const caido = instalacion && estadoAddon?.responde === false;

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 shadow-sm">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 bg-slate-800 px-4 py-2 text-white">
          <a href="#/" className="flex items-center gap-2.5 rounded">
            <Stethoscope className="size-6 text-teal-300" aria-hidden="true" />
            <span>
              <span className="block text-base font-semibold leading-tight">Estación clínica simulada</span>
              <span className="block text-xs text-slate-300">Historia clínica genérica de atención primaria · no es un producto real</span>
            </span>
          </a>
          <nav className="flex items-center gap-1" aria-label="Barra de herramientas">
            <Pestana href="#/" activa={ruta.vista === "historia"} icono={CalendarDays}>
              Agenda
            </Pestana>
            <Pestana href="#/configuracion/integraciones" activa={ruta.vista === "integraciones"} icono={Settings}>
              Configuración
            </Pestana>
            {instalacion?.app && (
              <button
                type="button"
                onClick={abrirModal}
                title={`Abrir ${addon} con ${pacienteAbierto ? `el paciente ${pacienteAbierto.id}` : "el cupo"} (add-on instalado)`}
                className="ml-2 inline-flex h-9 items-center gap-1.5 rounded bg-teal-600 px-3 text-sm font-semibold text-white ring-1 ring-inset ring-teal-300/40 hover:bg-teal-500"
              >
                <HeartPulse className="size-4" aria-hidden="true" />
                {addon}
                {caido && <span className="ml-1 rounded bg-red-600 px-1.5 py-0.5 text-[11px] font-semibold">no responde</span>}
              </button>
            )}
          </nav>
          <div className="ml-auto flex flex-wrap items-center gap-x-4 gap-y-1">
            <span className="flex items-center gap-1.5 text-sm text-slate-200" title="Profesional con la sesión abierta (simulado)">
              <UserRound className="size-4" aria-hidden="true" />
              {PROFESIONAL.nombre}
              <span className="text-xs text-slate-400">· {PROFESIONAL.rol}</span>
            </span>
            <span className="rounded bg-amber-300 px-2.5 py-1 text-sm font-bold text-amber-950">Simulación – datos sintéticos</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-slate-300 bg-white px-4 py-1.5 text-xs text-slate-600">
          <span>Fecha de la simulación: {agenda.data ? fecha(agenda.data.fecha) : "—"}</span>
          <span>Pacientes del cupo: {agenda.data ? agenda.data.pacientes.length : "—"}</span>
          <span className="flex items-center gap-1.5">
            <PlugZap className="size-3.5" aria-hidden="true" />
            {instalacion ? (
              <>
                Add-on instalado: <strong className="font-semibold text-slate-900">{addon}</strong>
                <span className="font-mono">({instalacion.url})</span>
              </>
            ) : (
              <>
                Ningún add-on instalado ·{" "}
                <a href="#/configuracion/integraciones" className="font-semibold text-teal-800 hover:underline">
                  Configuración → Integraciones
                </a>
              </>
            )}
          </span>
        </div>
        {caido && !avisoOculto && (
          <div className="flex flex-wrap items-start gap-x-3 gap-y-1 border-b border-red-300 bg-red-50 px-4 py-2 text-sm text-red-900" role="alert">
            <Unplug className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <span className="min-w-0 flex-1">
              <strong className="font-semibold">El add-on {addon} no responde</strong> en <span className="font-mono text-xs">{instalacion.url}</span>.
              Compruebe que está arrancado (<span className="font-mono text-xs">start_addon</span>). La estación sigue funcionando, pero sin apoyo a la
              decisión.
            </span>
            <button type="button" onClick={() => comprobarAddon()} className="rounded bg-white px-2.5 py-0.5 font-semibold text-red-800 ring-1 ring-red-300 hover:bg-red-100">
              Reintentar
            </button>
            <a href="#/configuracion/integraciones" className="rounded bg-white px-2.5 py-0.5 font-semibold text-red-800 ring-1 ring-red-300 hover:bg-red-100">
              Integraciones
            </a>
            <button type="button" onClick={() => setAvisoOculto(true)} aria-label="Ocultar el aviso" className="rounded p-0.5 text-red-800 hover:bg-red-100">
              <X className="size-4" aria-hidden="true" />
            </button>
          </div>
        )}
      </header>

      <main className="px-4 pb-16 pt-4">
        {ruta.vista === "integraciones" ? (
          <Integraciones
            instalacion={instalacion}
            estadoAddon={estadoAddon}
            onInstalada={setInstalacion}
            onDesinstalar={quitarAddon}
            onEstadoAddon={informarEstado}
          />
        ) : (
          <div
            className={`mx-auto grid max-w-[1500px] items-start gap-3 lg:grid-cols-[15rem_minmax(0,1fr)] ${
              instalacion && abierto ? "xl:grid-cols-[15rem_minmax(0,1fr)_23rem]" : ""
            }`}
          >
            <Agenda agenda={agenda} id={abierto} />
            {abierto ? (
              <>
                <Historia id={abierto} />
                {instalacion && (
                  <div className="lg:col-start-2 xl:sticky xl:top-28 xl:col-start-3 xl:max-h-[calc(100vh-8rem)] xl:overflow-y-auto">
                    <PanelCds id={abierto} instalacion={instalacion} onAbrirAddon={abrirModal} onEstadoAddon={informarEstado} />
                  </div>
                )}
              </>
            ) : (
              <div className="rounded-md border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
                <UserRound className="mx-auto size-8 text-slate-400" aria-hidden="true" />
                <p className="mt-2 text-sm font-semibold text-slate-900">Abre un paciente de la agenda</p>
                <p className="mx-auto mt-1 max-w-md text-sm text-slate-600">
                  {instalacion ? (
                    <>
                      Al abrir la historia, la estación lanza el hook <span className="font-mono">patient-view</span> de CDS Hooks y muestra la tarjeta de {addon}{" "}
                      en el panel lateral.
                    </>
                  ) : (
                    <>Esta estación no tiene ningún add-on de apoyo a la decisión instalado: solo muestra la historia clínica.</>
                  )}
                </p>
                <a href="#/paciente/P003" className="mt-4 inline-flex items-center gap-1.5 rounded bg-teal-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-teal-800">
                  Abrir a José Fernández (P003)
                  <ArrowRight className="size-4" aria-hidden="true" />
                </a>
              </div>
            )}
          </div>
        )}
      </main>

      {modal && instalacion?.app && <ModalAddon instalacion={instalacion} paciente={pacienteAbierto} onCerrar={cerrarModal} />}
    </div>
  );
}
