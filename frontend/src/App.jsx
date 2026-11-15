import { useCallback, useEffect, useState } from "react";
import { Download } from "lucide-react";
import { api } from "./api.js";
import { issEstacion, lanzamiento } from "./launch.js"; // antes de leer la ruta: puede abrir la ficha del paciente en contexto
import Header from "./components/Header.jsx";
import CupoView from "./components/CupoView.jsx";
import PatientView from "./components/PatientView.jsx";
import RulesView from "./components/RulesView.jsx";

const NAV = [{ href: "#/parametros", view: "parametros", label: "Parámetros del protocolo" }];

// El add-on no tiene datos propios ni elige cohorte: lee los del servidor FHIR de la estación clínica que lo
// ha abierto (`iss`) o, sin lanzamiento, los de la estación que la API tiene configurada.
const SEL = { iss: issEstacion };

function parseHash() {
  const [seg, id] = window.location.hash.replace(/^#\/?/, "").split("/");
  if (seg === "paciente" && id) return { view: "paciente", id: decodeURIComponent(id) };
  if (seg === "parametros") return { view: "parametros" };
  return { view: "cupo" };
}

export default function App() {
  const [route, setRoute] = useState(parseHash);
  // Cada cambio vuelve a pedir el cupo: al guardar parámetros (la API recalcula) o con "Actualizar"
  // (`refresh`: la API vuelve a leer el cupo de la estación).
  const [peticion, setPeticion] = useState({ n: 0, refresh: false });
  const [cupo, setCupo] = useState({ data: null, loading: true, error: null });
  const [filtro, setFiltro] = useState("TODOS");
  const [busqueda, setBusqueda] = useState("");

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
    setCupo((c) => ({ ...c, loading: true, error: null }));
    api
      .cupo(SEL, { refresh: peticion.refresh }, ctrl.signal)
      .then((data) => setCupo({ data, loading: false, error: null }))
      .catch((e) => e.name !== "AbortError" && setCupo({ data: null, loading: false, error: e.message }));
    return () => ctrl.abort();
  }, [peticion]);

  const recalcular = useCallback(() => setPeticion((p) => ({ n: p.n + 1, refresh: false })), []);
  const releer = useCallback(() => setPeticion((p) => ({ n: p.n + 1, refresh: true })), []);

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
          <CupoView cupo={cupo} onRetry={recalcular} filtro={filtro} onFiltro={setFiltro} busqueda={busqueda} onBusqueda={setBusqueda} />
        )}
        {route.view === "parametros" && <RulesView kpis={cupo.data?.kpis} recalculando={cupo.loading} onSaved={recalcular} />}
        {route.view === "paciente" && <PatientView id={route.id} sel={SEL} version={peticion.n} fuentes={cupo.data?.kpis.fonts} />}
      </main>
    </div>
  );
}
