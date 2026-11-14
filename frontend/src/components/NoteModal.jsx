import { useEffect, useRef, useState } from "react";
import { Check, ClipboardCopy, FileText, Send, X } from "lucide-react";

async function copiar(texto) {
  try {
    await navigator.clipboard.writeText(texto);
    return true;
  } catch {
    // Sin permiso de portapapeles (p. ej. http sin foco): se recurre al método clásico
    const area = document.createElement("textarea");
    area.value = texto;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    return ok;
  }
}

export default function NoteModal({ paciente, onClose }) {
  const [pestana, setPestana] = useState("nota");
  const [copiado, setCopiado] = useState(null);
  const cerrar = useRef(null);
  const docs = {
    nota: { titulo: "Nota clínica", icono: FileText, texto: paciente.nota_clinica_auto },
    volante: { titulo: "Volante", icono: Send, texto: paciente.volant_auto },
  };
  const actual = docs[pestana];

  useEffect(() => {
    const previo = document.activeElement;
    cerrar.current?.focus();
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      previo?.focus?.();
    };
  }, [onClose]);

  async function onCopiar() {
    const ok = await copiar(actual.texto);
    setCopiado(ok ? pestana : "error");
    setTimeout(() => setCopiado(null), 2500);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-clinic-900/50 p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-labelledby="modal-titulo" className="flex max-h-[90vh] w-full max-w-3xl flex-col rounded-lg bg-white shadow-2xl">
        <div className="flex items-start gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0 flex-1">
            <h2 id="modal-titulo" className="text-base font-semibold text-ink">
              Nota clínica y volante · {paciente.nom}
            </h2>
            <p className="text-xs text-muted">Borrador generado por reglas, sin IA generativa. Revísalo antes de pegarlo en la historia clínica.</p>
          </div>
          <button ref={cerrar} type="button" onClick={onClose} aria-label="Cerrar" className="rounded p-1.5 text-muted hover:bg-clinic-50">
            <X className="size-5" aria-hidden="true" />
          </button>
        </div>
        <div className="flex gap-1 border-b border-line px-5 pt-3" role="tablist">
          {Object.entries(docs).map(([id, d]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={pestana === id}
              onClick={() => setPestana(id)}
              className={`-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-semibold ${
                pestana === id ? "border-clinic-600 text-clinic-700" : "border-transparent text-muted hover:text-ink"
              }`}
            >
              <d.icono className="size-4" aria-hidden="true" />
              {d.titulo}
            </button>
          ))}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {actual.texto ? (
            <pre className="whitespace-pre-wrap rounded-md border border-line bg-clinic-50 p-4 font-sans text-sm leading-relaxed text-ink">{actual.texto}</pre>
          ) : (
            <p className="rounded-md border border-line bg-clinic-50 p-4 text-sm text-muted">
              No hay analíticas ni interconsultas que pedir para este paciente: no se necesita volante.
            </p>
          )}
        </div>
        <div className="flex items-center justify-end gap-3 border-t border-line px-5 py-3">
          <span className="mr-auto text-xs text-muted" role="status">
            {copiado === "error" && "No se pudo copiar: selecciona el texto y cópialo a mano."}
            {copiado && copiado !== "error" && "Copiado al portapapeles."}
          </span>
          <button type="button" onClick={onClose} className="rounded-md px-3 py-2 text-sm font-semibold text-clinic-700 hover:bg-clinic-50">
            Cerrar
          </button>
          <button
            type="button"
            onClick={onCopiar}
            disabled={!actual.texto}
            className="inline-flex items-center gap-2 rounded-md bg-clinic-600 px-4 py-2 text-sm font-semibold text-white hover:bg-clinic-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {copiado === pestana ? <Check className="size-4" aria-hidden="true" /> : <ClipboardCopy className="size-4" aria-hidden="true" />}
            Copiar {actual.titulo.toLowerCase()}
          </button>
        </div>
      </div>
    </div>
  );
}
