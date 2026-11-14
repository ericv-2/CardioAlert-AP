// Formato de números y fechas en castellano.
// El separador de miles se pone siempre (1.500): por defecto, "es-ES" no agrupa los números de 4 cifras.
export const num = (v, decimals = 0) => {
  if (v == null) return "—";
  const [entero, decimal] = Number(v)
    .toLocaleString("es-ES", { minimumFractionDigits: decimals, maximumFractionDigits: decimals, useGrouping: false })
    .split(",");
  const agrupado = entero.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return decimal == null ? agrupado : `${agrupado},${decimal}`;
};

export const pct = (v) => (v == null ? "—" : `${num(v, 1)}%`);

export const fecha = (iso) => {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
};

export const SEXO = { H: "Hombre", D: "Mujer" };

// Categorías de riesgo CV de la tabla 5 de la guía ESC 2021 (la única clasificación): siempre color + texto.
export const CATEGORIA_CV = {
  "Muy alto": "bg-red-50 text-red-800 ring-red-200",
  Alto: "bg-amber-50 text-amber-900 ring-amber-300",
  "Bajo-moderado": "bg-emerald-50 text-emerald-800 ring-emerald-200",
};

// Grupos del orden de la lista de trabajo (no son una clasificación de riesgo): texto corto para filtros.
export const GRUPO_CORTO = { 1: "Alertas urgentes", 2: "Muy alto sin tratar", 3: "Alto sin tratar", 4: "Resto" };

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
