import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { num, sinAcentos } from "../format.js";

const MAX_AGENDA = 150;

export default function Agenda({ agenda, id }) {
  const [busqueda, setBusqueda] = useState("");
  const pacientes = useMemo(() => {
    const q = sinAcentos(busqueda.trim());
    return (agenda.data?.pacientes ?? []).filter((p) => !q || sinAcentos(`${p.nombre} ${p.id}`).includes(q));
  }, [agenda.data, busqueda]);

  return (
    <nav className="rounded-md border border-slate-300 bg-white" aria-label="Pacientes del cupo">
      <div className="border-b border-slate-200 bg-slate-100 px-3 py-2">
        <h2 className="text-sm font-semibold text-slate-900">Agenda del cupo</h2>
        <label className="relative mt-2 block">
          <span className="sr-only">Buscar paciente</span>
          <Search className="pointer-events-none absolute left-2 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
          <input
            type="search"
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            placeholder="Nombre o n.º de historia"
            className="h-8 w-full rounded border border-slate-300 bg-white pl-8 pr-2 text-sm text-slate-900"
          />
        </label>
      </div>
      {agenda.error ? (
        <p className="p-3 text-sm text-red-800" role="alert">{agenda.error}</p>
      ) : !agenda.data ? (
        <p className="p-3 text-sm text-slate-500" role="status">Cargando la agenda…</p>
      ) : (
        <ul className="max-h-[72vh] overflow-auto text-sm">
          {pacientes.length === 0 && <li className="p-3 text-slate-500">Ningún paciente coincide.</li>}
          {pacientes.slice(0, MAX_AGENDA).map((p) => (
            <li key={p.id}>
              <a
                href={`#/paciente/${encodeURIComponent(p.id)}`}
                aria-current={p.id === id ? "page" : undefined}
                className={`flex items-baseline justify-between gap-2 border-l-4 px-3 py-1.5 ${
                  p.id === id ? "border-teal-600 bg-teal-50 font-semibold text-slate-900" : "border-transparent text-slate-800 hover:bg-slate-50"
                }`}
              >
                <span className="truncate">{p.nombre}</span>
                <span className="tabular whitespace-nowrap text-xs font-normal text-slate-500">
                  {p.id} · {p.edad} a
                </span>
              </a>
            </li>
          ))}
          {pacientes.length > MAX_AGENDA && (
            <li className="p-3 text-xs text-slate-500">
              Mostrando {MAX_AGENDA} de {num(pacientes.length)} pacientes: use el buscador para encontrar el resto.
            </li>
          )}
        </ul>
      )}
    </nav>
  );
}
