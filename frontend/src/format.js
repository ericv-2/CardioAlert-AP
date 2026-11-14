// Formato de números y fechas en castellano.
export const num = (v, decimals = 0) =>
  v == null ? "—" : Number(v).toLocaleString("es-ES", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

export const pct = (v) => (v == null ? "—" : `${num(v, 1)}%`);

export const fecha = (iso) => {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
};

export const SEXO = { H: "Hombre", D: "Mujer" };

// Semáforo de prioridad (nivel del motor) y categorías de riesgo: siempre color + texto.
export const NIVEL = {
  ALT: { texto: "ALT", largo: "Prioridad alta", chip: "bg-red-50 text-red-800 ring-red-200", dot: "bg-red-600" },
  MITJA: { texto: "MITJA", largo: "Prioridad media", chip: "bg-amber-50 text-amber-900 ring-amber-300", dot: "bg-amber-500" },
  BAIX: { texto: "BAIX", largo: "Prioridad baja", chip: "bg-emerald-50 text-emerald-800 ring-emerald-200", dot: "bg-emerald-600" },
};

export const CATEGORIA_CV = {
  "Riesgo muy alto": "bg-red-50 text-red-800 ring-red-200",
  "Riesgo alto": "bg-amber-50 text-amber-900 ring-amber-300",
  "Riesgo bajo-moderado": "bg-emerald-50 text-emerald-800 ring-emerald-200",
};

export const KDIGO = {
  verd: { dot: "bg-emerald-600", texto: "riesgo bajo" },
  groc: { dot: "bg-yellow-400", texto: "riesgo moderado" },
  taronja: { dot: "bg-orange-500", texto: "riesgo alto" },
  vermell: { dot: "bg-red-600", texto: "riesgo muy alto" },
};

export const ESTADO_RENAL = {
  normal: "Función renal normal",
  mrc: "Enfermedad renal crónica",
  pendent_confirmar: "Alteración pendiente de confirmar",
  possible_fra: "Caída aguda: descartar FRA",
  sense_dades: "Sin creatinina registrada",
};
