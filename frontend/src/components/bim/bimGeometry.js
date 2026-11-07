// Funções puras do BIM Studio (sem WebGL) — testáveis com Jest.

export const ORIGIN_STYLE = {
  declared: { label: "Declarada no modelo", short: "Declarada", cls: "bg-sky-500/15 text-sky-700 dark:text-sky-300 border-sky-500/30" },
  calculated: { label: "Calculada pela geometria", short: "Calculada", cls: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30" },
  estimated: { label: "Estimada (aproximação)", short: "Estimada", cls: "bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30" },
  manual: { label: "Corrigida manualmente", short: "Corrigida", cls: "bg-violet-500/15 text-violet-700 dark:text-violet-300 border-violet-500/30" },
};

export const CONFIDENCE_STYLE = {
  verificada: "bg-emerald-600 text-white",
  declarada: "bg-sky-500/15 text-sky-700 dark:text-sky-300",
  calculada: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  estimada: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  incompleta: "bg-red-500/15 text-red-700 dark:text-red-300",
};

// Cores por categoria (tons alinhados com verde/cobre/creme ConstruPilot)
export const CATEGORY_COLORS = {
  paredes: [0.87, 0.84, 0.78], portas: [0.72, 0.45, 0.25], janelas: [0.55, 0.75, 0.88],
  lajes: [0.66, 0.68, 0.66], pilares: [0.42, 0.52, 0.46], vigas: [0.42, 0.52, 0.46],
  coberturas: [0.72, 0.36, 0.24], escadas: [0.6, 0.58, 0.52], pavimentos: [0.8, 0.74, 0.62],
  revestimentos: [0.85, 0.82, 0.76], espacos: [0.36, 0.62, 0.48], estrutura: [0.42, 0.52, 0.46],
  fachadas: [0.55, 0.75, 0.88], guardas: [0.4, 0.4, 0.42], instalacoes: [0.85, 0.6, 0.2],
  mobiliario: [0.7, 0.6, 0.5], outros: [0.75, 0.73, 0.7],
};

/** Valida um elemento do bloco de geometria devolvido pela API. */
export function isValidMesh(el) {
  if (!el || !Array.isArray(el.p) || !Array.isArray(el.i)) return false;
  if (el.p.length === 0 || el.p.length % 3 !== 0 || el.i.length % 3 !== 0) return false;
  const n = el.p.length / 3;
  for (let k = 0; k < el.i.length; k += 1) if (el.i[k] < 0 || el.i[k] >= n) return false;
  return true;
}

/** Visibilidade de um elemento segundo filtros (pisos, categorias, ocultos, isolados). */
export function isVisible(meta, { storeys, categories, hidden, isolated }) {
  if (!meta) return true;
  if (isolated && isolated.size > 0) return isolated.has(meta.gid);
  if (hidden && hidden.has(meta.gid)) return false;
  if (categories && categories.size > 0 && !categories.has(meta.category)) return false;
  if (storeys && storeys.size > 0 && !storeys.has(meta.storey_gid || "_none")) return false;
  if (meta.category === "espacos" && !(categories && categories.has("espacos"))) return false;
  return true;
}

/** Caixa envolvente (coordenadas IFC, Z para cima) de um conjunto de posições planas. */
export function boundsOf(arrays) {
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  arrays.forEach((p) => {
    for (let k = 0; k < p.length; k += 3) {
      for (let a = 0; a < 3; a += 1) {
        const v = p[k + a];
        if (v < min[a]) min[a] = v;
        if (v > max[a]) max[a] = v;
      }
    }
  });
  if (!Number.isFinite(min[0])) return null;
  return { min, max, center: min.map((v, a) => (v + max[a]) / 2), size: Math.max(max[0] - min[0], max[1] - min[1], max[2] - min[2]) };
}

export function formatQty(value, unit) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const d = unit === "u" ? 0 : Math.abs(value) < 10 ? 3 : 2;
  return `${new Intl.NumberFormat("pt-PT", { maximumFractionDigits: d }).format(Number(value))} ${unit || ""}`.trim();
}

export function distance(a, b) {
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

// Textos por perfil profissional (a mesma ferramenta, linguagem adaptada)
export const PROFILE_COPY = {
  arquiteto: { label: "Arquiteto", tab: "modelo", intro: "Explore o modelo, as áreas por divisão e os materiais, e prepare as medições." },
  engenheiro: { label: "Engenheiro", tab: "medicoes", intro: "Propriedades técnicas, elementos estruturais e verificação das quantidades com a sua origem." },
  empresa: { label: "Empresa de construção", tab: "orcamento", intro: "Quantidades de trabalho, materiais, custos e orçamento — e o que mudou entre versões." },
  simples: { label: "Modo simples", tab: "modelo", intro: "Carregue o ficheiro do seu projeto e siga os passos: nós explicamos cada resultado." },
};

export const SIMPLE_STEPS = [
  "Carregue o ficheiro IFC do projeto (pedido ao arquiteto).",
  "Veja o edifício em 3D e confirme que está completo.",
  "Verifique as medições: as amarelas são aproximações, as vermelhas estão em falta.",
  "Associe cada grupo de elementos a um preço da sua biblioteca.",
  "Gere o orçamento e reveja-o no editor antes de o enviar.",
];
