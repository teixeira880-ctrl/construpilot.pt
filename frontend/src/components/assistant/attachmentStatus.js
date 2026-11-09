// Pièces jointes du composeur de l'Assistant BTP, reconnues AVANT l'envoi.
// Une seule description sert à trois endroits : la ligne de confirmation visible sous le champ de saisie,
// l'écran en direct envoyé à l'assistante vidéo (Aurora) et l'état exposé par window.__cpAssistant.
// Chaque fichier : nom, type (plan, devis, facture, CCTP, photo, document, dossier), pages, texte lu ou non,
// et s'il est nouveau (joint pour ce message) ou déjà dans le contexte de la conversation.

const KIND = {
  fr: { plan: "plan", quote: "devis", invoice: "facture", cctp: "CCTP", photo: "photo", document: "document", dossier: "dossier" },
  pt: { plan: "planta", quote: "orçamento", invoice: "fatura", cctp: "caderno de encargos", photo: "foto", document: "documento", dossier: "processo" },
  en: { plan: "plan", quote: "quote", invoice: "invoice", cctp: "specification", photo: "photo", document: "document", dossier: "folder" },
  es: { plan: "plano", quote: "presupuesto", invoice: "factura", cctp: "pliego", photo: "foto", document: "documento", dossier: "expediente" },
};
const TXT = {
  fr: { one: "1 fichier joint et reconnu", many: (n) => `${n} fichiers joints et reconnus`, ready: "l'Assistant BTP et Aurora les ont vus et les analyseront à l'envoi",
        uploading: "Import en cours… attendez la fin avant d'envoyer", pages: (n) => `${n} p.`, read: "texte lu", noText: "scan sans texte (lu en image)", fresh: "nouveau" },
  pt: { one: "1 ficheiro anexado e reconhecido", many: (n) => `${n} ficheiros anexados e reconhecidos`, ready: "o Assistente BTP e a Aurora já os viram e vão analisá-los ao enviar",
        uploading: "A importar… aguarde o fim antes de enviar", pages: (n) => `${n} pág.`, read: "texto lido", noText: "digitalização sem texto (lida como imagem)", fresh: "novo" },
  en: { one: "1 file attached and recognised", many: (n) => `${n} files attached and recognised`, ready: "the BTP Assistant and Aurora have seen them and will analyse them on send",
        uploading: "Uploading… wait until it finishes before sending", pages: (n) => `${n} p.`, read: "text read", noText: "scan without text (read as image)", fresh: "new" },
  es: { one: "1 archivo adjunto y reconocido", many: (n) => `${n} archivos adjuntos y reconocidos`, ready: "el Asistente BTP y Aurora ya los han visto y los analizarán al enviar",
        uploading: "Importando… espere a que termine antes de enviar", pages: (n) => `${n} pág.`, read: "texto leído", noText: "escaneo sin texto (leído como imagen)", fresh: "nuevo" },
};
const pick = (lang) => (TXT[lang] ? lang : "fr");

export function describeAttachments({ activePlans = [], activeDocs = [], pending = [], plans = [], docs = [], dossiers = [] } = {}) {
  const fresh = new Set(pending);
  const out = [];
  for (const id of activePlans) {
    const p = plans.find((x) => x.plan_id === id) || {};
    out.push({ id, name: p.filename || id, kind: "plan", pages: p.pages || p.page_count || null, has_text: null, new: fresh.has(id) });
  }
  for (const id of activeDocs) {
    const d = docs.find((x) => x.doc_id === id) || {};
    out.push({ id, name: d.filename || id, kind: d.kind || "document", pages: d.pages || null,
               has_text: typeof d.has_text === "boolean" ? d.has_text : null, mime: d.mime || null, new: fresh.has(id) });
  }
  for (const o of dossiers) {
    out.push({ id: o.dossier_id, name: o.name, kind: "dossier", files: o.count ?? o.done ?? null, total: o.total ?? null, busy: !!o.busy, new: true });
  }
  return out;
}

export function kindLabel(kind, lang) { return (KIND[pick(lang)] || KIND.fr)[kind] || kind; }

// Détail court d'un fichier : « devis · 3 pág. · texto lido · novo »
export function attachmentDetail(a, lang) {
  const t = TXT[pick(lang)];
  const bits = [kindLabel(a.kind, lang)];
  if (a.kind === "dossier" && a.total) bits.push(`${a.files ?? 0}/${a.total}`);
  if (a.pages) bits.push(t.pages(a.pages));
  if (a.has_text === true) bits.push(t.read);
  if (a.has_text === false && a.kind !== "photo") bits.push(t.noText);
  if (a.new) bits.push(t.fresh);
  return bits.join(" · ");
}

// Ligne de confirmation affichée avant l'envoi (null si rien n'est joint).
export function attachmentLine(list, { uploading = false, lang = "fr" } = {}) {
  const t = TXT[pick(lang)];
  if (uploading) return t.uploading;
  if (!list.length) return null;
  return `${list.length === 1 ? t.one : t.many(list.length)} — ${t.ready}.`;
}
