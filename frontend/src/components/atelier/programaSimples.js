// Programa detalhado (divisões com área, por piso) a partir das escolhas do modo simples — função pura, sem dependências.

// Nomes das divisões que o leitor de programa reconhece em cada língua.
const NOMES = {
  pt: { entrada: "Hall de entrada", sala: "Sala de estar e jantar", cozinha: "Cozinha", wc: "WC", escritorio: "Escritório", lavandaria: "Lavandaria",
        suite: "Suite", closet: "Closet", sde: "Casa de banho da suite", quarto: "Quarto", sdb: "Casa de banho", circ: "Escadas, circulação e paredes",
        rc: "Rés do chão", andar: "Primeiro andar", casa: "Moradia", garagem: (n) => `Garagem para ${n === 2 ? "dois automóveis" : "um automóvel"}`,
        piscina: "Piscina exterior de 8 × 4 m", jardim: "Jardim paisagístico", terraco: "Terraço com pérgola e zona de refeições exterior",
        cob: { plana: "Cobertura plana", duas: "Cobertura de duas águas", quatro: "Cobertura de quatro águas" },
        estilo: { moderno: "design moderno e minimalista", contemporaneo: "design contemporâneo", tradicional: "estilo tradicional português" },
        pisos: (n) => (n === 2 ? "de dois pisos" : "térrea"), quartos: (n) => `${n} quartos` },
  fr: { entrada: "Entrée", sala: "Séjour / salle à manger", cozinha: "Cuisine", wc: "WC", escritorio: "Bureau", lavandaria: "Buanderie",
        suite: "Suite parentale", closet: "Dressing", sde: "Salle d'eau parentale", quarto: "Chambre", sdb: "Salle de bains", circ: "Dégagement, escalier et murs",
        rc: "Rez-de-chaussée", andar: "Étage", casa: "Maison", garagem: (n) => (n === 2 ? "Double garage, 2 voitures" : "Garage 1 voiture"),
        piscina: "Piscine 8 x 4 m", jardim: "Jardin paysager", terraco: "Terrasse avec pergola et coin repas extérieur",
        cob: { plana: "Toit plat", duas: "Toiture 2 pans", quatro: "Toiture 4 pans" },
        estilo: { moderno: "design moderne et épuré", contemporaneo: "design contemporain", tradicional: "style traditionnel" },
        pisos: (n) => (n === 2 ? "en R+1" : "de plain-pied"), quartos: (n) => `${n} chambres` },
  en: { entrada: "Entrance", sala: "Living and dining room", cozinha: "Kitchen", wc: "WC", escritorio: "Office", lavandaria: "Laundry",
        suite: "Master bedroom", closet: "Walk-in closet", sde: "Bathroom en suite", quarto: "Bedroom", sdb: "Bathroom", circ: "Stairs, hallway and walls",
        rc: "Ground floor", andar: "First floor", casa: "House", garagem: (n) => (n === 2 ? "Two-car garage" : "Garage for one car"),
        piscina: "Swimming pool 8 x 4 m", jardim: "Landscaped garden", terraco: "Terrace with pergola and outdoor dining",
        cob: { plana: "Flat roof", duas: "Gable roof", quatro: "Hip roof" },
        estilo: { moderno: "modern minimalist design", contemporaneo: "contemporary design", tradicional: "traditional style" },
        pisos: (n) => (n === 2 ? "two-storey" : "single-storey"), quartos: (n) => `${n} bedrooms` },
};

// Mínimos usados pelo modo simples (acima do RGEU art. 66.º e do logement décent): nunca descer abaixo.
const MIN = { entrada: 3, sala: 16, cozinha: 8, wc: 2, escritorio: 7, lavandaria: 3, suite: 12, closet: 3, sde: 3.5, quarto: 10, sdb: 4.5 };
const BASE = { entrada: 6, sala: 30, cozinha: 12, wc: 2, escritorio: 10, lavandaria: 6, suite: 16, closet: 6, sde: 5, quarto: 12, sdb: 6 };
// Parte da área ocupada por circulações e paredes numa moradia corrente (medida no gerador: 30 a 35 %).
const K = 1.33;
const meio = (x) => Math.round(x * 2) / 2;
const fmt = (x, lang) => (lang === "en" ? String(x) : String(x).replace(".", ","));

/** Divisões do programa (mesma regra que o texto). */
function divisoes(o) {
  const dia = ["entrada", "sala", "cozinha", "wc"];
  if (o.escritorio) dia.push("escritorio");
  if (o.lavandaria) dia.push("lavandaria");
  const noite = [];
  if (o.suite && o.quartos >= 1) noite.push("suite", "closet", "sde");
  for (let i = 0; i < Math.max(0, o.quartos - (o.suite ? 1 : 0)); i += 1) noite.push("quarto");
  noite.push("sdb");
  if (o.quartos >= 4) noite.push("sdb");
  return { dia, noite };
}

/** Área de construção realista mínima para estas escolhas (divisões nos mínimos + circulações e paredes), em m². */
export function areaMinima(o) {
  const { dia, noite } = divisoes(o);
  const s = [...dia, ...noite].reduce((t, k) => t + MIN[k], 0);
  return Math.ceil((s * K * (o.pisos === 2 ? 1.25 : 1.08)) / 10) * 10;
}

/** Programa detalhado a partir das escolhas (função pura, testada). */
export function programaSimples(o, lang = "pt") {
  const N = NOMES[lang] || NOMES.pt;
  const L = [];
  const { dia, noite } = divisoes(o);
  const todas = [...dia, ...noite];
  const soma = todas.reduce((s, k) => s + BASE[k], 0);
  const f = Math.min(2.2, Math.max(0.7, (o.area / K / (o.pisos === 2 ? 1.18 : 1.1)) / soma));
  const area = (k) => meio(k === "wc" ? BASE.wc : Math.max(MIN[k], BASE[k] * f));
  const linhas = (lista) => {
    let nq = o.suite ? 1 : 0;
    let nb = 0;
    return lista.map((k) => {
      let nome = N[k];
      if (k === "quarto") { nq += 1; nome = `${N.quarto} ${nq}`; }
      if (k === "sdb") { nb += 1; nome = nb > 1 ? `${N.sdb} ${nb}` : N.sdb; }
      return [nome, area(k)];
    });
  };
  const bloco = (titulo, lista) => {
    const ls = linhas(lista);
    const s = ls.reduce((t, [, a]) => t + a, 0);
    const total = Math.round(s * K);
    L.push(`${titulo} — ${total} m²`);
    ls.forEach(([n, a]) => L.push(`* ${n}: ${fmt(a, lang)} m²`));
    L.push(`* ${N.circ}: ${fmt(meio(total - s), lang)} m²`);
    return total;
  };
  const cab = [];
  const pisos = o.pisos === 2 ? 2 : 1;
  const extra = [];
  if (o.garagem) extra.push(N.garagem(o.garagem));
  if (o.piscina) extra.push(N.piscina);
  if (o.terraco) extra.push(N.terraco);
  if (o.jardim) extra.push(N.jardim);
  extra.push(N.cob[o.cobertura] || N.cob.duas);
  let total;
  if (pisos === 2) {
    const t0 = bloco(N.rc, dia);
    L.push("");
    const t1 = bloco(N.andar, noite);
    total = t0 + t1;
  } else {
    total = bloco(N.rc, todas);
  }
  cab.push(`${N.casa} ${N.pisos(pisos)}, ${N.quartos(o.quartos)}, ${total} m², ${N.estilo[o.estilo] || N.estilo.moderno}.`);
  extra.forEach((e) => cab.push(`* ${e}.`));
  return [...cab, "", ...L].join("\n");
}

