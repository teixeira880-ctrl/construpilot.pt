// Textos da demonstração interativa da página inicial — Portugal (pt-PT, 3.ª pessoa formal).
// O componente DemoInterativa.jsx é idêntico no .pt e no .fr; só este ficheiro muda.
export const LOCALE = "pt-PT";
export const LANG_VOZ = "pt-PT";
export const D = {
  eyebrow: "EXPERIMENTE JÁ, SEM CRIAR CONTA",
  titulo: "Veja o ConstruPilot a trabalhar em 30 segundos.",
  sub: "Três exemplos reais do dia a dia, com dados fictícios. Nada é gravado.",
  tabs: { voz: "Relato de obra por voz", orcamento: "Orçamento de exemplo", mapa: "Avanço da obra" },
  aviso: "Demonstração com dados fictícios: nada é gravado nem enviado.",
  // voz
  voz_intro: "O encarregado conta o dia como falaria ao telefone. O ConstruPilot separa tudo e prepara os registos — que o utilizador confirma antes de gravar.",
  voz_ph: "Escreva ou dite o relato do dia…",
  ditar: "Ditar", a_ouvir: "A ouvir… fale agora", parar: "Parar",
  exemplos: [
    "Hoje estiveram 4 pessoas da equipa do Rui e 2 eletricistas. Chegaram 40 sacos de cimento. Gastámos 12 sacos de cimento no reboco. O reboco da cozinha está a 60%. O João trabalhou sem capacete. Temos uma dúvida para o arquiteto sobre a cota da soleira. Veio o fiscal às 15h.",
    "Recebemos 2,5 m3 de areia e 3 paletes de tijolo. A pintura do quarto 1 está concluída. Choveu à tarde e parámos uma hora.",
  ],
  usar_exemplo: "Usar um exemplo", interpretar: "Interpretar",
  t_diario: "Diário de obra", t_stock: "Stock", t_seg: "Segurança", t_pedido: "Pedido ao arquiteto", t_avanco: "Avanço da obra",
  entrada: "Entrada", saida: "Saída", trabalhos: "Trabalhos", efetivos: "Efetivos", visitas: "Visitas", ocorrencias: "Ocorrências",
  confirmar: "Confirmar e gravar", confirmado: "Registado na obra (demonstração)", nada: "Escreva um relato com o que aconteceu em obra.",
  // orçamento
  orc_intro: "Um orçamento de remodelação calculado a partir da área: mude a área e o nível de acabamento e veja os totais mudar.",
  area: "Área a remodelar", acabamento: "Acabamento", niveis: { economico: "Económico", medio: "Médio", premium: "Premium" },
  artigo: "Artigo", qtd: "Qtd.", un: "Un.", preco: "Preço", total: "Total", subtotal: "Subtotal sem IVA", iva: "IVA 23 %", total_iva: "Total com IVA",
  precos_ficticios: "Preços fictícios de exemplo. Na plataforma, os preços vêm da biblioteca da sua empresa.",
  linhas: [
    ["Demolições e remoção de entulho", "m²", 1.0, 18],
    ["Paredes em gesso cartonado", "m²", 0.6, 32],
    ["Instalação elétrica completa", "m²", 1.0, 45],
    ["Canalização (águas e esgotos)", "vg", null, 2400],
    ["Pavimento", "m²", 1.0, 38],
    ["Pintura de paredes e tetos", "m²", 3.2, 9],
    ["Caixilharia", "un", 0.08, 650],
  ],
  // mapa
  mapa_intro: "Clique numa divisão e arraste o cursor: a cor e o avanço global atualizam-se, como no Mapa da obra.",
  global: "Avanço global", divisoes: [["Sala", 4, 6, 44, 44, 70], ["Cozinha", 50, 6, 46, 44, 45], ["WC", 4, 52, 28, 42, 100], ["Quarto 1", 34, 52, 62, 42, 15]],
  escolha_divisao: "Escolha uma divisão na planta.", legenda: "por iniciar · em curso · avançado · concluído",
  // fim
  cta: "Experimentar com os meus projetos", cta_sub: "Sem fidelização.",
};

// Vocabulário do mini-intérprete (demonstração no navegador, sem servidor).
export const VOC = {
  numeros: { um: 1, uma: 1, dois: 2, duas: 2, tres: 3, quatro: 4, cinco: 5, seis: 6, sete: 7, oito: 8, nove: 9, dez: 10, vinte: 20, trinta: 30, quarenta: 40, cinquenta: 50, cem: 100 },
  unidades: { sacos: "saco", saco: "saco", m3: "m³", m2: "m²", paletes: "palete", palete: "palete", kg: "kg", unidades: "un", tijolos: "un" },
  entrada: /\b(cheg\w*|receb\w*|entreg\w*|descarreg\w*|vieram)\b/,
  saida: /\b(gast\w*|us\w*mos|consum\w*|aplic\w*|betonamos)\b/,
  pessoas: /(\d+|\w+) (pessoas|homens|trabalhadores|operarios|eletricistas|pedreiros|canalizadores)( da equipa (do |da |de )?(\w+))?/,
  seg: /\bsem (capacete|colete|arnes|botas|luvas|epi)|\bacidente|\bquase caiu|\bcaiu\b/,
  pedido: /\bduvida\b|\besclarec|\bperguntar\b|\bfalta (o |a )?(pormenor|cota)/,
  visita: /\bvisita|\bveio (o|a) (fiscal|arquitet|dono|cliente)|\besteve ca\b/,
  ocorrencia: /\bchuv|\bchoveu|\bparamos|\batras|\bavaria|\bfaltou/,
  concluido: /\b(concluid|terminad|acabad)/,
  ligacao: ["de", "do", "da"], fim: ["e", "no", "na", "para", "em", "que", "ao"],
};
