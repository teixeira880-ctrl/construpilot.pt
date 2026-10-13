import { useI18n } from "@/context/I18nContext";

const copy = {
  fr: {
    table: "Tableau de la réponse — défilement horizontal",
    activity: "Assistant : travail en cours", activityOffline: "Assistant : suivi indisponible",
    backgroundHint: "Le travail continue, même si vous changez de page. Retrouvez la réponse ici ou dans vos notifications.",
    eyebrow: "CONSTRUPILOT · ASSISTANT", title: "Avançons sur votre chantier.",
    intro: "Un devis à préparer, un plan à vérifier, un compte rendu à rédiger. Partons de votre besoin.",
    subtitle: "Votre espace de travail BTP", context: "Contexte", contextTitle: "Documents et réglages",
    contextHint: "Choisissez les pièces à utiliser et la manière de répondre.",
    quote: "Préparer un devis", quoteDesc: "Structurer les postes et le chiffrage.",
    analyse: "Examiner un plan", analyseDesc: "Lire les cotes et repérer les points à vérifier.",
    report: "Rédiger un compte rendu", reportDesc: "Organiser vos notes et les prochaines actions.",
    mail: "Préparer un courrier", mailDesc: "Trouver les mots justes pour votre client.",
    solve: "Une question technique ?", solveDesc: "Comprendre un problème et comparer les solutions.",
    draftHint: "Chaque raccourci prépare une demande que vous pouvez modifier.",
    attach: "Joindre", existing: "Choisir un document déjà importé", image: "Préparer un visuel",
    webOn: "Web activé", webOff: "Web désactivé", you: "Vous", loading: "Ouverture de la conversation…",
    historyHint: "Retrouvez le fil de vos projets", documents: "Documents liés", listen: "Écouter",
  },
  pt: {
    table: "Tabela da resposta — deslocamento horizontal",
    activity: "Assistente: trabalho em curso", activityOffline: "Assistente: acompanhamento indisponível",
    backgroundHint: "O trabalho continua mesmo que mude de página. Encontre a resposta aqui ou nas notificações.",
    eyebrow: "CONSTRUPILOT · ASSISTENTE", title: "Vamos avançar com a sua obra.",
    intro: "Um orçamento a preparar, uma planta a verificar ou um relatório a redigir. Comecemos pelo que precisa.",
    subtitle: "O seu espaço de trabalho para a obra", context: "Contexto", contextTitle: "Documentos e opções",
    contextHint: "Escolha os documentos a utilizar e o tipo de resposta.",
    quote: "Preparar um orçamento", quoteDesc: "Organizar os trabalhos e os custos.",
    analyse: "Examinar uma planta", analyseDesc: "Ler as cotas e identificar o que verificar.",
    report: "Redigir um relatório", reportDesc: "Organizar notas e próximas ações.",
    mail: "Preparar uma mensagem", mailDesc: "Encontrar as palavras certas para o cliente.",
    solve: "Uma questão técnica?", solveDesc: "Compreender um problema e comparar soluções.",
    draftHint: "Cada atalho prepara um pedido que pode editar.",
    attach: "Anexar", existing: "Escolher um documento já importado", image: "Preparar uma imagem",
    webOn: "Internet ativa", webOff: "Internet desativada", you: "Você", loading: "A abrir a conversa…",
    historyHint: "Retome os seus projetos", documents: "Documentos associados", listen: "Ouvir",
  },
  en: {
    table: "Response table — scroll horizontally",
    activity: "Assistant: work in progress", activityOffline: "Assistant: updates unavailable",
    backgroundHint: "Work continues when you leave this page. Find the reply here or in your notifications.",
    eyebrow: "CONSTRUPILOT · ASSISTANT", title: "Move your project forward.",
    intro: "A quote to prepare, a plan to check or a site report to write. Start with what you need.",
    subtitle: "Your construction workspace", context: "Context", contextTitle: "Documents and settings",
    contextHint: "Choose the supporting documents and response style.",
    quote: "Prepare a quote", quoteDesc: "Organise the work items and costs.",
    analyse: "Review a plan", analyseDesc: "Read dimensions and identify what needs checking.",
    report: "Write a site report", reportDesc: "Organise notes and next steps.",
    mail: "Draft a message", mailDesc: "Find the right words for your client.",
    solve: "A technical question?", solveDesc: "Understand a problem and compare solutions.",
    draftHint: "Each shortcut prepares a request you can edit.",
    attach: "Attach", existing: "Choose an imported document", image: "Prepare an image",
    webOn: "Web on", webOff: "Web off", you: "You", loading: "Opening conversation…",
    historyHint: "Pick up where you left off", documents: "Linked documents", listen: "Listen",
  },
};

export function useStudioCopy() {
  const { lang } = useI18n();
  return (key) => copy[lang]?.[key] || copy.fr[key] || key;
}
