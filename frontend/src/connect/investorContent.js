// Conteúdo PÚBLICO do percurso investidor. Nada de cap table, dados de clientes, documentos financeiros
// internos ou montantes não validados. A tração indica data e fonte; atualizar aqui quando mudar.
export const TRACTION_AS_OF = "2026-11-06";

export const INVESTOR = {
  overview: {
    title: { pt: "Visão geral", en: "Overview", fr: "Vue d'ensemble" },
    body: {
      pt: "A ConstruPilot é uma plataforma SaaS para profissionais da construção que liga a planta, as medições, o orçamento e o acompanhamento económico da obra. Está em funcionamento em construpilot.pt (Portugal) e construpilot.fr (França), em versão beta.",
      en: "ConstruPilot is a SaaS platform for construction professionals that connects the drawing, the take-off, the estimate and the job's financial follow-up. It runs on construpilot.pt (Portugal) and construpilot.fr (France), in beta.",
      fr: "ConstruPilot est une plateforme SaaS pour les professionnels du bâtiment qui relie le plan, le métré, le devis et le suivi économique du chantier. Elle fonctionne sur construpilot.pt (Portugal) et construpilot.fr (France), en version bêta.",
    },
  },
  problem: {
    title: { pt: "O problema", en: "The problem", fr: "Le problème" },
    body: {
      pt: "Nas pequenas e médias empresas de construção, medir plantas e preparar orçamentos continua a ser feito à mão ou em folhas de cálculo. É lento, sujeito a erros e desligado do controlo de custos — as margens perdem-se sem que se perceba onde.",
      en: "In small and mid-sized construction firms, measuring drawings and preparing estimates is still done by hand or in spreadsheets. It is slow, error-prone and disconnected from cost control — margins leak without anyone seeing where.",
      fr: "Dans les TPE/PME du bâtiment, le métré et le chiffrage se font encore à la main ou sur tableur. C'est lent, sujet aux erreurs et déconnecté du suivi des coûts — les marges fuient sans qu'on sache où.",
    },
  },
  solution: {
    title: { pt: "A solução", en: "The solution", fr: "La solution" },
    body: {
      pt: "Um fluxo único: importar a planta, calibrar e medir, validar quantidades, aplicar os preços da empresa, controlar margens e acompanhar a obra. Os cálculos são feitos por motores determinísticos testados; a IA assiste, o profissional valida.",
      en: "One workflow: import the drawing, calibrate and measure, validate quantities, apply the company's prices, control margins and follow the job. Calculations run on tested deterministic engines; AI assists, the professional validates.",
      fr: "Un flux unique : importer le plan, calibrer et métrer, valider les quantités, appliquer les prix de l'entreprise, maîtriser les marges et suivre le chantier. Les calculs reposent sur des moteurs déterministes testés ; l'IA assiste, le professionnel valide.",
    },
  },
  segments: {
    title: { pt: "Segmentos de clientes", en: "Customer segments", fr: "Segments clients" },
    items: {
      pt: ["Empreiteiros e empresas de remodelação (2 a 50 pessoas)", "Especialidades: pintura, eletricidade, canalização/AVAC", "Medidores-orçamentistas", "Gabinetes de arquitetura e engenharia (sobretudo como parceiros)", "Particulares, como porta de entrada"],
      en: ["Contractors and renovation firms (2 to 50 people)", "Trades: painting, electrical, plumbing/HVAC", "Quantity surveyors / estimators", "Architecture and engineering firms (mainly as partners)", "Homeowners, as an entry point"],
      fr: ["Entreprises générales et de rénovation (2 à 50 personnes)", "Corps d'état : peinture, électricité, plomberie/CVC", "Métreurs / économistes", "Architectes et bureaux d'études (surtout en partenariat)", "Particuliers, comme porte d'entrée"],
    },
  },
  model: {
    title: { pt: "Modelo comercial", en: "Business model", fr: "Modèle économique" },
    body: {
      pt: "Subscrição SaaS B2B por níveis (Solo, Professional, Business e Enterprise sob consulta), com faturação mensal ou anual. Os preços em vigor estão na página Planos; a cobrança automática ainda não está ativa.",
      en: "Tiered B2B SaaS subscription (Solo, Professional, Business, and Enterprise on request), billed monthly or yearly. Current prices are on the Plans page; automated billing is not yet live.",
      fr: "Abonnement SaaS B2B par paliers (Solo, Professional, Business, et Enterprise sur demande), facturation mensuelle ou annuelle. Les tarifs en vigueur sont sur la page Offres ; la facturation automatique n'est pas encore active.",
    },
  },
  traction: {
    title: { pt: "Tração", en: "Traction", fr: "Traction" },
    source: { pt: "Fonte: dados internos declarados pelos fundadores", en: "Source: internal figures reported by the founders", fr: "Source : chiffres internes déclarés par les fondateurs" },
    items: {
      pt: ["Plataforma em beta pública em Portugal e em França", "86 utilizadores beta registados (44 em .pt, 42 em .fr)", "Cerca de 80 projetos criados durante a beta, parte deles em testes dos próprios fundadores", "Ainda sem clientes pagantes; empresa autofinanciada pelos fundadores"],
      en: ["Platform in public beta in Portugal and France", "86 registered beta users (44 on .pt, 42 on .fr)", "About 80 projects created during the beta, some of them founders' own tests", "No paying customers yet; company self-funded by the founders"],
      fr: ["Plateforme en bêta publique au Portugal et en France", "86 utilisateurs bêta inscrits (44 sur .pt, 42 sur .fr)", "Environ 80 projets créés pendant la bêta, dont une partie par les fondateurs en test", "Pas encore de clients payants ; société autofinancée par les fondateurs"],
    },
  },
  risks: {
    title: { pt: "Principais riscos", en: "Key risks", fr: "Principaux risques" },
    items: {
      pt: ["Conversão de utilizadores beta em clientes pagantes ainda por demonstrar", "Dependência de fornecedores externos de IA para funções assistidas", "Responsabilidade técnica: estudos de engenharia exigem parceria com gabinetes habilitados", "Equipa fundadora reduzida face ao ritmo de desenvolvimento"],
      en: ["Conversion of beta users into paying customers not yet proven", "Dependence on external AI providers for assisted features", "Technical liability: engineering studies require licensed partner firms", "Small founding team relative to the development pace"],
      fr: ["Conversion des utilisateurs bêta en clients payants encore à démontrer", "Dépendance à des fournisseurs d'IA externes pour les fonctions assistées", "Responsabilité technique : les études d'ingénierie exigent des bureaux d'études partenaires", "Équipe fondatrice réduite au regard du rythme de développement"],
    },
  },
  meeting: {
    title: { pt: "Proposta de reunião", en: "Meeting proposal", fr: "Proposition de rendez-vous" },
    body: {
      pt: "Propomos uma primeira conversa com os fundadores. Documentação confidencial (financeira e societária) só é partilhada depois dessa conversa e mediante autorização expressa.",
      en: "We propose a first conversation with the founders. Confidential documents (financial and corporate) are only shared after that conversation and with explicit authorisation.",
      fr: "Nous proposons un premier échange avec les fondateurs. Les documents confidentiels (financiers et juridiques) ne sont partagés qu'après cet échange et sur autorisation explicite.",
    },
  },
  deck: { pt: "Resumo executivo (pitch deck público, PDF)", en: "Executive summary (public pitch deck, PDF)", fr: "Résumé exécutif (pitch deck public, PDF)" },
};
