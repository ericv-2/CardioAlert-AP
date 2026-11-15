// Formato de números y fechas en castellano.
export const num = (v, decimals = 0) => {
  if (v == null) return "—";
  const [entero, decimal] = Number(v)
    .toLocaleString("es-ES", { minimumFractionDigits: decimals, maximumFractionDigits: decimals, useGrouping: false })
    .split(",");
  const agrupado = entero.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return decimal == null ? agrupado : `${agrupado},${decimal}`;
};

export const fecha = (iso) => {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
};

export const fechaHora = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${d.toLocaleDateString("es-ES")} ${d.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" })}`;
};

export const SEXO = { H: "Hombre", D: "Mujer" };

export const sinAcentos = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
