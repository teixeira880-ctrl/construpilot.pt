// Comandos em linguagem corrente para o Estúdio de Projeto: «fachada em granito», «telhado de 4 águas», «2 pisos»,
// «casa com 12 x 9», «janela da sala com 3 m», «acrescenta uma janela na fachada esquerda», «cor da fachada bege».
// Aplicação imediata e local (sem IA): cada frase dá alterações explícitas; o que não for percebido é dito.

const norm = (s) => (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
const num = (s) => Number(String(s).replace(",", "."));

const FACHADAS = [["granito", "granito"], ["pedra", "granito"], ["xisto", "xisto"], ["madeira", "madeira"], ["ripado", "madeira"],
  ["tijolo", "tijolo"], ["betao", "betao"], ["reboco", "reboco_branco"], ["branca", "reboco_branco"], ["misto", "misto_granito_reboco"]];
const CORES = { branca: "#f2f0ea", branco: "#f2f0ea", bege: "#e6d6b8", creme: "#efe4c8", cinza: "#9ea3a8", cinzento: "#9ea3a8",
  "cinza escuro": "#4a4f55", antracite: "#2f3235", preta: "#1d1f21", preto: "#1d1f21", amarela: "#e8c66a", amarelo: "#e8c66a",
  terracota: "#b86a45", ocre: "#c9963f", azul: "#5a7fa8", verde: "#6f8f6a", vermelha: "#9b3a2e", vermelho: "#9b3a2e", castanho: "#6b4a32" };
const COMP = ["sala", "cozinha", "quarto", "suite", "escritorio", "wc", "entrada", "lavandaria"];
const FACH_V = { frente: "frente", principal: "frente", tardoz: "tardoz", traseira: "tardoz", esquerda: "esquerda", direita: "direita" };

function cor(t) {
  const hex = t.match(/#[0-9a-f]{6}\b/);
  if (hex) return hex[0];
  const nome = Object.keys(CORES).sort((a, b) => b.length - a.length).find((k) => new RegExp(`\\b${k}\\b`).test(t));
  return nome ? CORES[nome] : null;
}

/** Anexo novo encostado ao lado livre da casa (direita, senão esquerda, senão tardoz), dentro do lote. */
export function novoAnexo(vol, nome = "Garagem", l = 6, w = 5.5) {
  const L = Number(vol.footprint_l_m) || 10, W = Number(vol.footprint_w_m) || 8;
  const ss = Number(vol.setback_side_m) || 3, sf = Number(vol.setback_front_m) || 5;
  const pl = Number(vol.plot_l_m) || 0, pw = Number(vol.plot_w_m) || 0;
  if (!pl || ss + L + 1 + l <= pl) return { name: nome, l_m: l, w_m: w, h_m: 3, x_m: ss + L + 1, y_m: sf };
  if (ss - 1 - l >= 0) return { name: nome, l_m: l, w_m: w, h_m: 3, x_m: ss - 1 - l, y_m: sf };
  return { name: nome, l_m: l, w_m: w, h_m: 3, x_m: ss, y_m: Math.min(sf + W + 1, Math.max(0, (pw || sf + W + 1 + w) - w)) };
}

/** Devolve { vol, estilo, vaos, feito: [frases], falhou: bool } a partir do estado atual. */
export function aplicarComando(texto, { vol, estilo, vaos }) {
  const t = norm(texto);
  const feito = [];
  let v = { ...vol }, e = { ...estilo }, vs = vaos.map((x) => ({ ...x }));

  // dimensões e pisos
  const dim = t.match(/(\d+(?:[.,]\d+)?)\s*(?:m\s*)?x\s*(\d+(?:[.,]\d+)?)\s*m?\b/);
  if (dim && /casa|implanta|planta|dimens|medida|edificio|construc/.test(t)) {
    v.footprint_l_m = num(dim[1]); v.footprint_w_m = num(dim[2]);
    feito.push(`Casa com ${dim[1]} × ${dim[2]} m`);
  }
  const pisos = t.match(/\b(\d|um|dois|tres)\s*pisos?\b/);
  if (pisos) { const n = { um: 1, dois: 2, tres: 3 }[pisos[1]] || Number(pisos[1]); v.levels = n; feito.push(`${n} piso${n > 1 ? "s" : ""}`); }
  const pd = t.match(/(?:pe[- ]?direito|piso a piso)\D{0,6}(\d+(?:[.,]\d+)?)/);
  if (pd) { v.storey_h_m = num(pd[1]); feito.push(`Piso a piso ${pd[1]} m`); }

  // forma da casa e anexos
  if (/\bem l\b|forma de l|formato l|casa em l/.test(t)) { v.shape = "l"; feito.push("Casa em L"); }
  else if (/\bem t\b|forma de t|casa em t/.test(t)) { v.shape = "t"; feito.push("Casa em T"); }
  else if (/retangular|rectangular/.test(t)) { v.shape = "rectangle"; feito.push("Casa retangular"); }
  const anexoM = t.match(/(garagem|anexo|arrumos|telheiro|alpendre)/);
  if (anexoM && /(acrescent|adicion|poe|mete|nov|quero|com)/.test(t) && !/(remove|retira|tira|sem)/.test(t)) {
    const nome = { garagem: "Garagem", anexo: "Anexo", arrumos: "Arrumos", telheiro: "Telheiro", alpendre: "Alpendre" }[anexoM[1]];
    const dimA = t.match(/(\d+(?:[.,]\d+)?)\s*(?:m\s*)?x\s*(\d+(?:[.,]\d+)?)/);
    v.blocks = [...(v.blocks || []), novoAnexo(v, nome, dimA ? num(dimA[1]) : (nome === "Garagem" ? 6 : 4), dimA ? num(dimA[2]) : (nome === "Garagem" ? 5.5 : 3))];
    feito.push(`${nome} acrescentad${nome === "Garagem" ? "a" : "o"}`);
  } else if (anexoM && /(remove|retira|tira|sem)/.test(t) && (v.blocks || []).length) {
    v.blocks = []; feito.push("Anexos removidos");
  }

  // cobertura
  if (/(4|quatro)\s*aguas/.test(t)) { e.telhado = "quatro_aguas"; feito.push("Telhado de 4 águas"); }
  else if (/(2|duas)\s*aguas/.test(t)) { e.telhado = "duas_aguas"; feito.push("Telhado de 2 águas"); }
  else if (/(1|uma)\s*agua/.test(t)) { e.telhado = "uma_agua"; feito.push("Telhado de 1 água"); }
  else if (/(telhado|cobertura)\s*(plan[ao]|em terraco)|terraco/.test(t)) { e.telhado = "plana"; e.cobertura = "plana_seixo"; feito.push("Cobertura plana"); }
  const incl = t.match(/inclina\w*\D{0,6}(\d+(?:[.,]\d+)?)\s*%/);
  if (incl) { e.inclinacao_pct = num(incl[1]); feito.push(`Inclinação ${incl[1]} %`); }
  const bei = t.match(/beira[ld]\w*\D{0,6}(\d+(?:[.,]\d+)?)/);
  if (bei) { e.beiral_m = num(bei[1]); feito.push(`Beiral ${bei[1]} m`); }
  if (/telha\s*preta/.test(t)) { e.cobertura = "telha_preta"; feito.push("Telha preta"); }
  else if (/telha\s*(vermelha|ceramica|lusa|marselha)/.test(t)) { e.cobertura = "telha_ceramica"; feito.push("Telha cerâmica"); }
  else if (/zinco/.test(t)) { e.cobertura = "zinco"; feito.push("Cobertura em zinco"); }

  // fachada e caixilharia
  if (/fachada|parede|revest/.test(t)) {
    const f = FACHADAS.find(([k]) => new RegExp(`\\b${k}`).test(t));
    if (f && !/cor\b/.test(t)) { e.fachada = f[1]; feito.push(`Fachada: ${f[0]}`); }
    const c = cor(t);
    if (c && (/cor|pinta/.test(t) || !f)) { e.cor_fachada = c; feito.push(`Cor da fachada ${c}`); }
  }
  if (/caixilh|aluminio|janelas? (pretas?|brancas?|antracite)/.test(t)) {
    if (/madeira/.test(t)) { e.caixilharia = "madeira"; feito.push("Caixilharia em madeira"); }
    else if (/pvc/.test(t)) { e.caixilharia = "pvc_branco"; feito.push("Caixilharia PVC branco"); }
    else if (/branc/.test(t)) { e.caixilharia = "aluminio_branco"; feito.push("Caixilharia branca"); }
    else if (/pret|antracite|escur/.test(t)) { e.caixilharia = "aluminio_antracite"; feito.push("Caixilharia antracite"); }
    const c = cor(t);
    if (c && /cor/.test(t)) { e.cor_caixilharia = c; feito.push(`Cor da caixilharia ${c}`); }
  }
  if (/telhado|cobertura|telha/.test(t) && /cor/.test(t)) { const c = cor(t); if (c) { e.cor_cobertura = c; feito.push(`Cor da cobertura ${c}`); } }

  // vãos
  const comp = COMP.find((k) => new RegExp(`\\b${k}`).test(t));
  const larg = t.match(/(?:com|de|para)\s*(\d+(?:[.,]\d+)?)\s*m\b/);
  const fachM = Object.keys(FACH_V).find((k) => new RegExp(`fachada\\s+(?:da\\s+|de\\s+)?${k}|\\b${k}\\b`).test(t));
  const pisoM = t.match(/(?:piso|andar)\s*(\d)/);
  if (/(janela|porta|envidracado|vao)/.test(t) && /(acrescent|adicion|poe|mete|nova)/.test(t) && fachM) {
    const piso = pisoM ? Number(pisoM[1]) : (/r[ée]s|res do chao/.test(t) ? 0 : 0);
    const w = larg ? num(larg[1]) : 1.2, porta = /porta/.test(t);
    const comprimento = ["esquerda", "direita"].includes(FACH_V[fachM]) ? v.footprint_w_m : v.footprint_l_m;
    const x0 = Math.max(0.4, comprimento / 2 - w / 2);
    vs.push({ fachada: FACH_V[fachM], piso, tipo: porta ? "porta" : (w >= 2.4 ? "envidracado" : "janela"), compartimento: "",
      x0, x1: x0 + w, z0: porta ? 0 : 0.9, z1: 2.3, _rel: true });
    feito.push(`${porta ? "Porta" : "Janela"} de ${w} m na fachada ${FACH_V[fachM]}${piso ? `, piso ${piso}` : ""}`);
  } else if (/(janela|porta|envidracado|vao)/.test(t) && /(remove|retira|tira|apaga|elimina)/.test(t)) {
    const antes = vs.length;
    vs = vs.filter((o) => !((comp && norm(o.compartimento).includes(comp)) || (!comp && fachM && o.fachada === FACH_V[fachM])));
    if (vs.length < antes) feito.push(`${antes - vs.length} vão(s) removido(s)`);
  } else if (comp && larg && /(janela|envidracado|vao|porta)/.test(t)) {
    const w = num(larg[1]);
    let n = 0;
    vs = vs.map((o) => {
      if (!norm(o.compartimento).includes(comp)) return o;
      n += 1; const c = (o.x0 + o.x1) / 2; return { ...o, x0: c - w / 2, x1: c + w / 2, tipo: w >= 2.4 ? "envidracado" : o.tipo };
    });
    if (n) feito.push(`Vão(s) de ${comp} com ${w} m (${n})`);
  }
  return { vol: v, estilo: e, vaos: vs, feito, falhou: feito.length === 0 };
}

export const EXEMPLOS = [
  "fachada em granito", "telhado de 4 águas com beiral de 0,8 m", "2 pisos", "casa com 12 x 9 m", "telha preta",
  "cor da fachada bege", "caixilharia antracite", "janela da sala com 3,5 m", "acrescenta uma janela na fachada esquerda",
  "casa em L", "acrescenta uma garagem",
];
