// Converte qualquer erro (incl. 422 FastAPI/Pydantic com `detail` em lista de objetos) num texto legível.
export function errorText(err, fallback = "Ocorreu um erro.") {
  const d = err?.response?.data?.detail ?? err?.detail ?? err;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map(e => (e?.msg ? `${(e.loc || []).slice(1).join(".")}: ${e.msg}` : String(e))).join(" · ");
  if (d && typeof d === "object") return d.msg || d.message || fallback;
  return fallback;
}
