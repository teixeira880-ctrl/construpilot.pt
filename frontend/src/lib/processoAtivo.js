// Processo de obra ativo: o fio que acompanha o trabalho de app em app.
// Guardado por conta (user_id) e partilhado entre separadores do mesmo browser.
const CHAVE = "cp:processo-ativo";

const ler = () => {
  try { return JSON.parse(window.localStorage.getItem(CHAVE) || "null") || null; } catch { return null; }
};

export function processoAtivo(userId) {
  const p = ler();
  return p && p.userId === userId && p.chantierId ? p : null;
}

export function definirProcessoAtivo(userId, chantierId, nome = "") {
  try {
    window.localStorage.setItem(CHAVE, JSON.stringify({ userId, chantierId, nome, desde: Date.now() }));
    window.dispatchEvent(new Event("cp:processo-ativo"));
  } catch { /* armazenamento indisponível: o processo continua a seguir pelo URL */ }
}

export function limparProcessoAtivo() {
  try {
    window.localStorage.removeItem(CHAVE);
    window.dispatchEvent(new Event("cp:processo-ativo"));
  } catch { /* nada a fazer */ }
}

// Parâmetros que não identificam um trabalho (navegação, marketing…).
const IGNORAR = new Set(["chantier", "tab", "lang", "from", "origem", "utm_source", "utm_medium", "utm_campaign"]);

/** Parâmetros que identificam o trabalho aberto (ex.: ?projet=arch_…, ?open=plan_…). */
export function paramsDoTrabalho(search) {
  const out = {};
  new URLSearchParams(search || "").forEach((v, k) => {
    if (!IGNORAR.has(k) && v && Object.keys(out).length < 8) out[k] = String(v).slice(0, 120);
  });
  return out;
}

/** Junta ?chantier= a um URL interno sem perder os outros parâmetros. */
export function comProcesso(to, chantierId) {
  if (!chantierId || !to || !to.startsWith("/")) return to;
  const [base, hash = ""] = to.split("#");
  const [path, qs = ""] = base.split("?");
  const sp = new URLSearchParams(qs);
  sp.set("chantier", chantierId);
  return `${path}?${sp.toString()}${hash ? `#${hash}` : ""}`;
}
