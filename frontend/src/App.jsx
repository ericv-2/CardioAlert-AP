import { useCallback, useEffect, useState } from "react";
import { api } from "./api.js";
import Header from "./components/Header.jsx";
import CupoView from "./components/CupoView.jsx";

function parseHash() {
  const [seg, id] = window.location.hash.replace(/^#\/?/, "").split("/");
  if (seg === "paciente" && id) return { view: "paciente", id: decodeURIComponent(id) };
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
      </main>
    </div>
  );
}
