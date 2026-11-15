import { useCallback, useEffect, useRef, useState } from "react";
import { BellRing, Download } from "lucide-react";
import { api } from "./api.js";
import { issEstacion, lanzamiento } from "./launch.js"; // antes de leer la ruta: puede abrir la ficha del paciente en contexto
import Header from "./components/Header.jsx";
import CupoView from "./components/CupoView.jsx";
import PatientView from "./components/PatientView.jsx";
import PruebasView from "./components/PruebasView.jsx";
import RulesView from "./components/RulesView.jsx";
import ActividadView from "./components/ActividadView.jsx";

const NAV = [
  { href: "#/pruebas", view: "pruebas", label: "Pruebas pendientes" },
  { href: "#/actividad", view: "actividad", label: "Registro de actividad" },
  { href: "#/parametros", view: "parametros", label: "Parámetros del protocolo" },
];

// El add-on no tiene datos propios ni elige cohorte: lee los del servidor FHIR de la estación clínica que lo
// ha abierto (`iss`) o, sin lanzamiento, los de la estación que la API tiene configurada.
const SEL = { iss: issEstacion };

function parseHash() {
  const [seg, id] = window.location.hash.replace(/^#\/?/, "").split("/");
  if (seg === "paciente" && id) return { view: "paciente", id: decodeURIComponent(id) };
  if (seg === "parametros") return { view: "parametros" };
  if (seg === "pruebas") return { view: "pruebas" };
  if (seg === "actividad") return { view: "actividad" };
  return { view: "cupo" };
}

export default function App() {
  const [route, setRoute] = useState(parseHash);
  // Cada cambio vuelve a pedir el cupo: al guardar parámetros (la API recalcula) o con "Actualizar"
  // (`refresh`: la API vuelve a leer el cupo de la estación).
  const [peticion, setPeticion] = useState({ n: 0, refresh: false, silencioso: false });
  const [aviso, setAviso] = useState(null); // "Datos nuevos de la estación" (poll)
  const versionVista = useRef(null); // versión del cupo en memoria de la API que se está mostrando
  const [cupo, setCupo] = useState({ data: null, loading: true, error: null });
  const [filtro, setFiltro] = useState("TODOS");
  const [busqueda, setBusqueda] = useState("");
  const [filtroEstado, setFiltroEstado] = useState("TODOS");

  useEffect(() => {
    const onHash = () => {
      setRoute(parseHash());
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    if (!peticion.silencioso) setCupo((c) => ({ ...c, loading: true, error: null }));
    api
      .cupo(SEL, { refresh: peticion.refresh }, ctrl.signal)
      .then((data) => {
        setCupo({ data, loading: false, error: null });
        api.estados(SEL).then((e) => (versionVista.current = e.versio_cupo)).catch(() => {});
      })
      .catch((e) => e.name !== "AbortError" && setCupo({ data: null, loading: false, error: e.message }));
    return () => ctrl.abort();
  }, [peticion]);

  const recalcular = useCallback(() => setPeticion((p) => ({ n: p.n + 1, refresh: false })), []);
  // Un cambio de estado solo toca los estados y «Hoy»: no se vuelve a pedir el cupo entero
  const refrescarEstados = useCallback(() => {
    api
      .estados(SEL)
      .then((e) =>
        setCupo((c) => (c.data ? { ...c, data: { ...c.data, estats: e.estats, llista_avui: e.llista_avui, recompte_estats: e.recompte_estats } } : c)),
      )
      .catch(() => {});
  }, []);
  const releer = useCallback(() => setPeticion((p) => ({ n: p.n + 1, refresh: true })), []);

  // Poll ligero: la API se entera sola de los datos nuevos de la estación (FHIR Subscription, o al leer un
  // paciente). Si su cupo en memoria ha cambiado, se vuelve a pedir sin spinner (y la ficha abierta, también).
  useEffect(() => {
    const reloj = setInterval(() => {
      if (document.hidden) return;
      api
        .estados(SEL)
        .then((e) => {
          if (versionVista.current != null && e.versio_cupo !== versionVista.current) {
            versionVista.current = e.versio_cupo;
            setAviso(new Date());
            setPeticion((p) => ({ n: p.n + 1, refresh: false, silencioso: true }));
          } else {
            setCupo((c) => (c.data ? { ...c, data: { ...c.data, estats: e.estats, llista_avui: e.llista_avui, recompte_estats: e.recompte_estats } } : c));
          }
        })
        .catch(() => {});
    }, 4000);
    return () => clearInterval(reloj);
  }, []);
  useEffect(() => {
    if (!aviso) return undefined;
    const t = setTimeout(() => setAviso(null), 8000);
    return () => clearTimeout(t);
  }, [aviso]);

  return (
    <div className="min-h-screen">
      <Header
        route={route}
        meta={cupo.data?.meta}
        loading={cupo.loading}
        sinDatos={Boolean(cupo.error)}
        onReleer={releer}
        nav={NAV}
        lanzamiento={lanzamiento}
        extra={
          <a
            href={api.excelUrl(SEL)}
            download="cupo_evaluado.xlsx"
            className="inline-flex h-9 items-center gap-2 rounded-md bg-white px-3 text-sm font-semibold text-clinic-700 shadow-sm hover:bg-clinic-50"
          >
            <Download className="size-4" aria-hidden="true" />
            Descargar Excel (.xlsx)
          </a>
        }
      />
      <main className="mx-auto max-w-[1440px] px-4 pb-16 pt-5 lg:px-6">
        {route.view === "cupo" && (
          <CupoView
            cupo={cupo}
            onRetry={recalcular}
            filtro={filtro}
            onFiltro={setFiltro}
            busqueda={busqueda}
            onBusqueda={setBusqueda}
            filtroEstado={filtroEstado}
            onFiltroEstado={setFiltroEstado}
          />
        )}
        {route.view === "pruebas" && <PruebasView cupo={cupo} sel={SEL} onRetry={recalcular} />}
        {route.view === "actividad" && <ActividadView sel={SEL} version={peticion.n} />}
        {route.view === "parametros" && <RulesView kpis={cupo.data?.kpis} recalculando={cupo.loading} onSaved={recalcular} />}
        {route.view === "paciente" && <PatientView id={route.id} sel={SEL} version={peticion.n} fuentes={cupo.data?.kpis.fonts} onEstado={refrescarEstados} onRecalculado={recalcular} />}
      </main>
      {aviso && (
        <div className="fixed bottom-4 right-4 z-50 flex max-w-sm items-start gap-2 rounded-md border border-clinic-200 bg-white px-4 py-3 text-sm shadow-lg" role="status">
          <BellRing className="mt-0.5 size-4 shrink-0 text-clinic-600" aria-hidden="true" />
          <span>
            <strong className="font-semibold">Datos nuevos de la estación clínica.</strong> Lista «Hoy» y cupo actualizados a las{" "}
            {aviso.toLocaleTimeString("es-ES")} sin que nadie abra al paciente.
          </span>
        </div>
      )}
    </div>
  );
}
