import { useCallback, useEffect, useState } from "react";
import { Download } from "lucide-react";
import { api } from "./api.js";
import { lanzamiento } from "./launch.js"; // antes de leer la ruta: puede abrir la ficha del paciente en contexto
import Header from "./components/Header.jsx";
import CupoView from "./components/CupoView.jsx";
import PatientView from "./components/PatientView.jsx";
import RulesView from "./components/RulesView.jsx";

const NAV = [{ href: "#/parametros", view: "parametros", label: "Parámetros del protocolo" }];

function parseHash() {
  const [seg, id] = window.location.hash.replace(/^#\/?/, "").split("/");
  if (seg === "paciente" && id) return { view: "paciente", id: decodeURIComponent(id) };
  if (seg === "parametros") return { view: "parametros" };
  return { view: "cupo" };
}

export default function App() {
  const [route, setRoute] = useState(parseHash);
  const [source, setSource] = useState("local");
  // La cohorte inicial se puede fijar en la URL: http://localhost:5173/?cohort=realista
  const [cohort, setCohort] = useState(() => (new URLSearchParams(window.location.search).get("cohort") === "realista" ? "realista" : "demo"));
  const [cohorts, setCohorts] = useState(null); // cohortes disponibles (GET /api/cohorts)
  const [version, setVersion] = useState(0); // sube al guardar parámetros: fuerza recalcular el cupo
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
    api
      .cohorts(ctrl.signal)
      .then((d) => setCohorts(d.cohorts))
      .catch(() => {});
    return () => ctrl.abort();
  }, []);

  // Los pacientes de una cohorte no existen en la otra: al cambiar, se vuelve a la lista y se limpian los filtros.
  const cambiarCohorte = useCallback((nueva) => {
    setCohort(nueva);
    if (nueva === "realista") setSource("local"); // la cohorte realista solo existe en local
    setFiltro("TODOS");
    setBusqueda("");
    setCupo({ data: null, loading: true, error: null });
    const { view } = parseHash();
    if (view === "paciente") window.location.hash = "#/";
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    setCupo((c) => ({ ...c, loading: true, error: null }));
    api
      .cupo({ source, cohort }, ctrl.signal)
      .then((data) => setCupo({ data, loading: false, error: null }))
      .catch((e) => e.name !== "AbortError" && setCupo({ data: null, loading: false, error: e.message }));
    return () => ctrl.abort();
  }, [source, cohort, version]);

  const recalcular = useCallback(() => setVersion((v) => v + 1), []);
  const sel = { source, cohort }; // la escala la fija rules.yaml: ESC automático + REGICOR de referencia

  return (
    <div className="min-h-screen">
      <Header
        route={route}
        source={source}
        onSource={setSource}
        cohort={cohort}
        onCohort={cambiarCohorte}
        cohorts={cohorts}
        meta={cupo.data?.meta}
        loading={cupo.loading}
        nav={NAV}
        lanzamiento={lanzamiento}
        extra={
          <a
            href={api.excelUrl(sel)}
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
            sel={sel}
            onRetry={recalcular}
            filtro={filtro}
            onFiltro={setFiltro}
            busqueda={busqueda}
            onBusqueda={setBusqueda}
          />
        )}
        {route.view === "parametros" && <RulesView kpis={cupo.data?.kpis} recalculando={cupo.loading} onSaved={recalcular} />}
        {route.view === "paciente" && <PatientView id={route.id} sel={sel} version={version} fuentes={cupo.data?.kpis.fonts} />}
      </main>
    </div>
  );
}
