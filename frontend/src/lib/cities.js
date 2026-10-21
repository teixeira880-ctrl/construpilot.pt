/**
 * Páginas locais SEO — uma rota por cidade portuguesa.
 * Conteúdo pensado para pesquisas «orçamento obras {cidade}».
 * Valores €/m² = ordens de grandeza indicativas de remodelação (2026), a confirmar por orçamento.
 */

const mk = (o) => ({ ...o, heroImage: o.heroImage || "https://images.unsplash.com/photo-1555881400-74d7acaacd8b?w=1600&q=80" });

export const CITIES = {
  lisboa: mk({
    slug: "lisboa", name: "Lisboa", region: "Área Metropolitana de Lisboa", department: "Distrito de Lisboa", postalPrefix: "1",
    priceRange: "650 – 1 200", priceStandard: 900,
    heroImage: "https://images.unsplash.com/photo-1585208798174-6cedd86e019a?w=1600&q=80",
    lat: 38.7223, lng: -9.1393,
    zipcodes: ["1000", "1100", "1150", "1200", "1250", "1300", "1350", "1400", "1500", "1600", "1700", "1800", "1900", "1990"],
    artisans: 14200, surface: "100 km²",
    typicalProject: "Remodelação total de apartamento T2 pombalino (70 m²)",
    typicalPrice: "55 000 – 85 000 €",
    localTips: [
      "Baixa Pombalina e zonas históricas: obras em fachadas e estrutura exigem controlo prévio da Câmara Municipal de Lisboa (e parecer da DGPC em imóveis classificados).",
      "Prédios em propriedade horizontal: intervenções em partes comuns ou paredes resistentes requerem autorização da assembleia de condóminos.",
      "Reabilitação de habitação: IVA a 6 % na mão de obra e materiais da empreitada quando enquadrada na verba 2.27 do CIVA — confirmar requisitos.",
    ],
  }),
  porto: mk({
    slug: "porto", name: "Porto", region: "Área Metropolitana do Porto", department: "Distrito do Porto", postalPrefix: "4",
    priceRange: "600 – 1 100", priceStandard: 820,
    heroImage: "https://images.unsplash.com/photo-1555881400-74d7acaacd8b?w=1600&q=80",
    lat: 41.1579, lng: -8.6291,
    zipcodes: ["4000", "4050", "4100", "4150", "4200", "4250", "4300", "4350"],
    artisans: 11800, surface: "41 km²",
    typicalProject: "Reabilitação de casa burguesa em granito (T3, 110 m²)",
    typicalPrice: "80 000 – 130 000 €",
    localTips: [
      "Centro Histórico (Património Mundial UNESCO): projetos sujeitos a apreciação reforçada pela Câmara Municipal do Porto.",
      "Paredes de granito e pavimentos em madeira: prever diagnóstico estrutural antes de abrir vãos ou alterar cargas.",
      "Áreas de Reabilitação Urbana (ARU): benefícios fiscais possíveis (IMI, IMT, IVA a 6 %) — confirmar junto da Câmara.",
    ],
  }),
  braga: mk({
    slug: "braga", name: "Braga", region: "Norte (Minho)", department: "Distrito de Braga", postalPrefix: "47",
    priceRange: "500 – 950", priceStandard: 700,
    lat: 41.5454, lng: -8.4265, zipcodes: ["4700", "4705", "4710", "4715"],
    artisans: 5200, surface: "183 km²",
    typicalProject: "Remodelação de moradia T3 dos anos 80 (140 m²)",
    typicalPrice: "70 000 – 110 000 €",
    localTips: [
      "Clima húmido do Minho: dar prioridade ao tratamento de humidades, ventilação e caixilharia com corte térmico.",
      "Moradias antigas: verificar a conformidade da instalação elétrica com as RTIEBT antes da remodelação.",
      "Licenciamento: obras de alteração interior sem afetar estrutura podem estar isentas de controlo prévio (RJUE) — confirmar.",
    ],
  }),
  coimbra: mk({
    slug: "coimbra", name: "Coimbra", region: "Centro", department: "Distrito de Coimbra", postalPrefix: "30",
    priceRange: "480 – 900", priceStandard: 680,
    lat: 40.2033, lng: -8.4103, zipcodes: ["3000", "3020", "3030", "3040"],
    artisans: 4100, surface: "319 km²",
    typicalProject: "Remodelação de apartamento T2 na Alta (75 m²)",
    typicalPrice: "45 000 – 70 000 €",
    localTips: [
      "Alta e Sofia (Património Mundial): intervenções exteriores sujeitas a parecer.",
      "Edifícios antigos com alvenaria de pedra: diagnóstico de fissuras e humidades recomendado.",
      "Apoios à eficiência energética: verificar avisos do Fundo Ambiental em vigor.",
    ],
  }),
  faro: mk({
    slug: "faro", name: "Faro", region: "Algarve", department: "Distrito de Faro", postalPrefix: "80",
    priceRange: "600 – 1 150", priceStandard: 850,
    lat: 37.0194, lng: -7.9322, zipcodes: ["8000", "8005"],
    artisans: 3900, surface: "202 km²",
    typicalProject: "Remodelação de moradia com piscina (T3, 150 m²)",
    typicalPrice: "95 000 – 160 000 €",
    localTips: [
      "Verões quentes: privilegiar isolamento da cobertura, sombreamento exterior e ventilação cruzada.",
      "Zona costeira: escolher materiais e ferragens resistentes à corrosão salina.",
      "Época alta turística: planear obras ruidosas fora do período de verão em zonas de alojamento local.",
    ],
  }),
  setubal: mk({
    slug: "setubal", name: "Setúbal", region: "Península de Setúbal", department: "Distrito de Setúbal", postalPrefix: "29",
    priceRange: "520 – 950", priceStandard: 720,
    lat: 38.5244, lng: -8.8882, zipcodes: ["2900", "2910"],
    artisans: 3600, surface: "230 km²",
    typicalProject: "Remodelação de apartamento T3 (90 m²)",
    typicalPrice: "50 000 – 80 000 €",
    localTips: [
      "Proximidade do estuário: atenção à impermeabilização de fundações e caves.",
      "Edifícios dos anos 60-80: verificar redes de águas e esgotos em ferro galvanizado.",
      "Condomínios: obras em fachadas e coberturas exigem deliberação da assembleia.",
    ],
  }),
  aveiro: mk({
    slug: "aveiro", name: "Aveiro", region: "Centro (Região de Aveiro)", department: "Distrito de Aveiro", postalPrefix: "38",
    priceRange: "500 – 920", priceStandard: 700,
    lat: 40.6405, lng: -8.6538, zipcodes: ["3800", "3810"],
    artisans: 3300, surface: "198 km²",
    typicalProject: "Reabilitação de moradia Arte Nova (T3, 130 m²)",
    typicalPrice: "85 000 – 140 000 €",
    localTips: [
      "Fachadas Arte Nova e azulejo: restauro com técnicas tradicionais e parecer municipal.",
      "Terrenos baixos e ria: prever drenagem e barreiras contra humidade ascensional.",
      "Reabilitação em ARU: possível IVA a 6 % — confirmar enquadramento.",
    ],
  }),
  funchal: mk({
    slug: "funchal", name: "Funchal", region: "Região Autónoma da Madeira", department: "Madeira", postalPrefix: "90",
    priceRange: "600 – 1 100", priceStandard: 830,
    lat: 32.6669, lng: -16.9241, zipcodes: ["9000", "9004", "9020", "9050", "9060"],
    artisans: 2700, surface: "76 km²",
    typicalProject: "Remodelação de apartamento T2 com vista mar (80 m²)",
    typicalPrice: "55 000 – 90 000 €",
    localTips: [
      "Madeira: taxas de IVA próprias (22 % / 12 % / 5 %) — o orçamento deve aplicar a taxa regional.",
      "Encostas acentuadas: custos de acesso e transporte de materiais a prever no orçamento.",
      "Zona sísmica e ventos fortes: reforçar fixações de coberturas e caixilharia.",
    ],
  }),
};

export const CITY_LIST = Object.values(CITIES);
export const getCity = (slug) => CITIES[slug];
