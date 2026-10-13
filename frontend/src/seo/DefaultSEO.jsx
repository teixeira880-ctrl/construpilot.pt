import { HeadTags } from "@/components/SEO";

// Défauts par route publique — une page peut les surcharger avec son propre <SEO>.
export const ROUTE_SEO = {
  "/": { title: "Orçamentos de obras com IA e estimativa de remodelação", description: "Orçamente, compare preços de materiais e estime a sua remodelação com o assistente IA da construção.", ptPath: "/" },
  "/particuliers": { title: "Estimar as suas obras: orçamento claro e detalhado", description: "Particulares: estime a sua remodelação, compare os orçamentos recebidos e acompanhe a sua obra com o ConstruPilot.", ptPath: "/particuliers" },
  "/metre": { title: "Editor de plantas IA: da planta ao orçamento", description: "Importe uma planta DWG ou PDF, obtenha as quantidades e um orçamento aos seus preços. Rastreabilidade completa das hipóteses.", ptPath: "/metre" },
  "/portugal": { title: "Orçamentos de obra com IA em Portugal", description: "Estime a sua obra, compare preços de materiais e prepare orçamentos profissionais com IVA e NIF.", lang: "pt", ptPath: "/" },
  "/investisseurs": { title: "Investidores: a plataforma IA da construção", description: "Números-chave, visão e roteiro do ConstruPilot, a plataforma IA de orçamentos e obras." },
  "/fonctionnalites": { title: "Funcionalidades ConstruPilot", description: "Estimativa IA, análise de plantas DWG, medição, orçamentos PDF, aprovisionamento e acompanhamento de obra: todo o ConstruPilot.", ptPath: "/fonctionnalites" },
  "/login": { title: "Iniciar sessão", description: "Inicie sessão no seu espaço ConstruPilot para encontrar os seus projetos, estimativas e orçamentos.", noindex: true },
  "/inscription": { title: "Criar conta", description: "Crie a sua conta ConstruPilot gratuita: estimativas, orçamentos e acompanhamento de obra num só lugar.", noindex: true },
  "/smart-project": { title: "Smart Project: estimativa IA detalhada", description: "Descreva o seu projeto, a IA propõe uma orçamentação capítulo a capítulo com quantidades e intervalos de preço.", ptPath: "/smart-project" },
  "/estimation": { title: "Estimador trabalhos gratuito", description: "Orçamente a sua obra em 3 passos: tipo de trabalhos, área, nível de acabamento. Estimativa imediata e gratuita.", ptPath: "/estimation" },
  "/calculateurs": { title: "Calculadoras de construção: betão, pladur, azulejo", description: "Calcule as quantidades de materiais (betão, blocos, pladur, azulejo, tinta) com as perdas incluídas.", ptPath: "/calculateurs" },
  "/prix": { title: "Comparador preços materiais construção", description: "Compare os preços dos materiais no Leroy Merlin, Maxmat, Bricomarché, AKI e noutras lojas.", ptPath: "/prix" },
  "/diy": { title: "Guias de obras passo a passo", description: "Tutoriais e guias práticos para realizar as suas obras, com conselhos de segurança e materiais necessários.", ptPath: "/diy" },
  "/coach": { title: "Coach travaux IA", description: "Faça as suas perguntas sobre obras à IA: ordem dos trabalhos, preços, regulamentação, escolha dos materiais.", ptPath: "/coach" },
  "/photo": { title: "Análise de fotografias de obras por IA", description: "Envie uma fotografia da sua divisão ou fachada: a IA identifica os trabalhos e propõe uma estimativa.", ptPath: "/photo" },
  "/tarifs": { title: "Preços e subscrições", description: "Oferta gratuita, Pro e Pro Business: escolha o plano ConstruPilot adequado à sua atividade.", ptPath: "/tarifs" },
  "/aide": { title: "Ajuda e assistência ConstruPilot", description: "Centro de ajuda: perguntas frequentes, assistente online, espaço do cliente e formulário de contacto com resposta em 1 dia útil.", ptPath: "/aide" },
  "/comparatif": { title: "Comparativo de softwares de orçamentos para a construção", description: "Compare o ConstruPilot com outros softwares de orçamentos e gestão de obra, função a função." },
  "/blog": { title: "Blogue de obras, orçamentos e construção", description: "Guias, preços e notícias da construção: remodelação, orçamentos, materiais, regulamentação e ferramentas IA.", ptPath: "/blog" },
  "/marketplace": { title: "Marketplace de profissionais da construção", description: "Encontre um profissional verificado para as suas obras ou receba pedidos qualificados perto de si.", ptPath: "/marketplace" },
  "/docs": { title: "Documentação e guias de utilização", description: "Primeiros passos no ConstruPilot: estimativa, plantas, orçamentos, faturas e integrações, explicados passo a passo.", ptPath: "/docs" },
  "/developpeurs": { title: "API para programadores", description: "Integre as estimativas e os orçamentos ConstruPilot nas suas ferramentas graças à API e aos webhooks.", ptPath: "/developpeurs" },
  "/enterprise": { title: "Oferta Empresa e marca branca", description: "Implemente o ConstruPilot para as suas equipas ou para os seus clientes: marca branca, SSO e acompanhamento dedicado.", ptPath: "/enterprise" },
  "/mentions-legales": { title: "Informação legal", description: "Editor, alojamento e informações legais do site ConstruPilot." },
  "/confidentialite": { title: "Política de privacidade", description: "Como o ConstruPilot recolhe, utiliza e protege os seus dados pessoais." },
  "/scanner-devis": { title: "Digitalizador de orçamentos IA", description: "Envie um orçamento em PDF: cada linha é comparada com os preços de mercado para saber se está correto ou demasiado caro.", noindex: true },
  "/cgv": { title: "Condições gerais de utilização e venda", description: "Condições de acesso, subscrições, cancelamento e responsabilidades do serviço ConstruPilot." },
  "/privacy": { title: "Política de privacidade das aplicações", description: "Dados recolhidos, autorizações pedidas pelas aplicações móveis, subcontratantes, conservação e eliminação de conta. Versão portuguesa e inglesa." },
  "/app-privacy": { title: "Política de privacidade das aplicações", description: "Dados recolhidos, autorizações pedidas pelas aplicações móveis, subcontratantes, conservação e eliminação de conta.", canonical: "/privacy" },
  "/confidentialite-apps": { title: "Política de privacidade das aplicações", description: "Dados recolhidos, autorizações pedidas pelas aplicações móveis, subcontratantes, conservação e eliminação de conta.", canonical: "/privacy" },
  "/reinitialiser": { title: "Reiniciar a minha palavra-passe", description: "Receba uma ligação para definir uma nova palavra-passe ConstruPilot.", noindex: true },
  "/radar": { title: "Radar de obras: licenças de construção", description: "Identifique as licenças de construção publicadas perto da sua empresa e estime o seu potencial de obra." },
};

export function DefaultSEO() {
  return <HeadTags routeDefaults={ROUTE_SEO} />;
}
