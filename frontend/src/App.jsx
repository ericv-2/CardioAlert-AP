import { useCallback, useEffect, useState } from "react";
import { Download } from "lucide-react";
import { api } from "./api.js";
import Header from "./components/Header.jsx";
import CupoView from "./components/CupoView.jsx";
import EstacionView from "./components/EstacionView.jsx";
import PatientView from "./components/PatientView.jsx";
import RulesView from "./components/RulesView.jsx";

const NAV = [
  { href: "#/estacion", view: "estacion", label: "Estación clínica simulada" },
  { href: "#/parametros", view: "parametros", label: "Parámetros del protocolo" },
];

function parseHash() {
  const [seg, id] = window.location.hash.replace(/^#\/?/, "").split("/");
  if (seg === "paciente" && id) return { view: "paciente", id: decodeURIComponent(id) };
  if (seg === "estacion") return { view: "estacion", id: id ? decodeURIComponent(id) : null };
  if (seg === "parametros") return { view: "parametros" };
  return { view: "cupo" };
}

export default function App() {
  const [route, setRoute] = useState(parseHash);
  const [source, setSource] = useState("local");
  const [scale, setScale] = useState("score2");
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
    setCupo((c) => ({ ...c, loading: true, error: null }));
    api
      .cupo({ source, scale }, ctrl.signal)
      .then((data) => setCupo({ data, loading: false, error: null }))
      .catch((e) => e.name !== "AbortError" && setCupo({ data: null, loading: false, error: e.message }));
    return () => ctrl.abort();
  }, [source, scale, version]);

  const recalcular = useCallback(() => setVersion((v) => v + 1), []);
  const sel = { source, scale };

  return (
    <div className="min-h-screen">
      <Header
        route={route}
        source={source}
        onSource={setSource}
        scale={scale}
        onScale={setScale}
        meta={cupo.data?.meta}
        loading={cupo.loading}
        nav={NAV}
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
        {route.view === "estacion" && <EstacionView id={route.id} cupo={cupo} sel={sel} />}
        {route.view === "paciente" &&<PatientView id={route.id} sel={sel} version={version} fuentes={cupo.data?.kpis.fonts} />}
      </main>
    </div>
  );
}
