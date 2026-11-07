// Synchro parole ↔ écran pour l'assistante vidéo (Lot 43).
//  1. Sous-titres en direct : ce que dit l'assistante (et ce que l'admin vient de dire) s'affiche sous la vidéo.
//  2. L'écran suit ses mots : quand elle nomme un bouton, un onglet ou un titre visible, il est montré aussitôt
//     (pointeur + contour), sans attendre un appel d'outil.
//  3. Navigation instantanée : « abre as faturas », « ouvre les devis », « open invoices »… l'admin a fini de parler,
//     la page s'ouvre tout de suite, pendant que l'agent réfléchit encore (il voit la page déjà ouverte et continue).
//  4. État de l'assistante (écoute / réfléchit / parle / agit) pour que l'admin sache toujours où elle en est.
import { clean, elements, inViewport, labelOf, norm, visible, inDock, txt } from "./avatarDom";

const TOPIC = "lk.transcription";
let room = null;
let opts = {};
let segs = new Map();           // segment → texte
let lastPointAt = 0;
let lastPointed = null;
let lastNavAt = 0;
let unsubs = [];

// ------------------------------------------------------------------ navigation vocale instantanée
const VERB = /^(?:(?:por favor|s'il (?:te|vous) pla[iî]t|please|podes|pode|peux[- ]tu|pouvez[- ]vous|can you|could you|puedes|quero|je veux|i want to|quiero)\s+)*(?:abre|abrir|abra|vai (?:a|à|às|ao|aos|para)|vamos (?:a|à|às|ao|aos|para)|mostra|mostrar|mostre|leva[- ]me (?:a|à|às|ao|aos|para)|ir (?:para|a|à|ao)|ouvre|ouvrir|va (?:sur|dans|à|a)|allons (?:sur|à|a)|montre|montrez|affiche|afficher|open|go to|show(?: me)?|take me to|abre|ve a|vamos a|muestra|ll[eé]vame a|apri|vai (?:su|a)|mostrami|öffne|zeige?)\b\s*(.*)$/i;
const NEG = /\b(n[aã]o|ne\b|pas\b|don'?t|do not|no abras|nicht|non aprire)\b/i;
// pages connues, en plusieurs langues (seulement si la page existe dans le menu affiché ou dans cette liste sûre)
const PAGES = [
  [/\b(fatura|faturas|facture|factures|invoice|invoices|factura|facturas|fattur[ae])\b/, "/factures"],
  [/\b(or[cç]amento|or[cç]amentos|devis|quote|quotes|presupuesto|presupuestos|preventiv[oi])\b/, "/devis"],
  [/\b(cliente|clientes|client|clients|customers?)\b/, "/clients"],
  [/\b(obra|obras|chantier|chantiers|jobsites?|sites?|cantier[ei])\b/, "/chantiers"],
  [/\b(assistente|assistant|asistente|assistente btp|assistant btp)\b/, "/assistant"],
  [/\b(painel|tableau de bord|dashboard|in[ií]cio|accueil|home|panel)\b/, "/dashboard"],
  [/\b(planeamento|planning|planificaci[oó]n|agenda|calend[aá]rio|calendrier)\b/, "/planning"],
  [/\b(plan|plano|plantas?|plans|m[eé]tr[eé]|medi[cç][oõ]es|take[- ]?offs?)\b/, "/plan"],
  [/\b(admin|administra[cç][aã]o|administration)\b/, "/admin"],
];

function menuMap() {
  const out = [];
  document.querySelectorAll('nav a[href^="/"], aside a[href^="/"], header a[href^="/"], [data-testid^="workspace-nav"] a[href^="/"]').forEach((a) => {
    if (inDock(a)) return;
    const href = a.getAttribute("href").split("#")[0];
    const label = norm(a.getAttribute("aria-label") || txt(a));
    if (href && label && label.length >= 3) out.push([label, href]);
  });
  return out;
}

export function navIntent(text) {
  const t = clean(text, 160);
  if (!t || t.length > 120 || NEG.test(t)) return null;
  const m = t.match(VERB);
  if (!m) return null;
  let rest = norm(m[1]);
  for (let i = 0; i < 3; i++) rest = rest.replace(/^(?:a|as|o|os|la|las|le|les|el|los|the|my|minhas?|meus?|mes|mis|i|gli|il|lo|die|der|das|page|pagina|ecra|onglet|tab)\s+/, "");
  if (!rest) return null;
  // 1) libellé exact d'un lien du menu affiché
  const menu = menuMap();
  const exact = menu.find(([label]) => label === rest || rest.startsWith(label + " ") || label.startsWith(rest));
  if (exact) return exact[1];
  // 2) mot-clé connu (multilingue)
  for (const [re, href] of PAGES) if (re.test(rest)) return href;
  return null;
}

function navigateNow(href) {
  if (!href || window.location.pathname === href) return false;
  opts.markAgentAction?.(2500);
  window.history.pushState({}, "", href);
  window.dispatchEvent(new PopStateEvent("popstate"));
  lastNavAt = Date.now();
  return true;
}

// ------------------------------------------------------------------ l'écran suit les mots de l'assistante
function speakables() {
  const main = document.querySelector("main") || document.body;
  const out = [];
  for (const el of elements({ limit: 120, viewportOnly: true })) {
    const k = norm(labelOf(el));
    if (k.length >= 4 && k.length <= 40) out.push([k, el]);
  }
  main.querySelectorAll("h1,h2,h3,[role=tab],th,label,dt").forEach((el) => {
    if (!visible(el) || !inViewport(el)) return;
    const k = norm(txt(el));
    if (k.length >= 4 && k.length <= 40) out.push([k, el]);
  });
  return out;
}

function followWords(text) {
  if (opts.isAgentActing?.()) return;              // elle pilote déjà l'écran : son geste prime
  const now = Date.now();
  if (now - lastPointAt < 700) return;
  const tail = ` ${norm(text.slice(-90))} `;
  let best = null, len = 0;
  for (const [k, el] of speakables()) {
    if (k.length > len && tail.includes(` ${k} `)) { best = el; len = k.length; }
  }
  if (!best || (best === lastPointed && now - lastPointAt < 4000)) return;
  lastPointed = best;
  lastPointAt = now;
  opts.point?.(best, { soft: true });
}

// ------------------------------------------------------------------ flux de transcription
async function onStream(reader, participantInfo) {
  const fromAdmin = participantInfo?.identity === room?.localParticipant?.identity;
  const a = reader.info?.attributes || {};
  const seg = a["lk.segment_id"] || reader.info?.id || String(Math.random());
  const final = a["lk.transcription_final"] === "true";
  let text = "";
  try {
    for await (const chunk of reader) {
      text += chunk;
      segs.set(seg, text);
      if (!fromAdmin) {
        opts.onCaption?.({ who: "agent", text: clean(text.slice(-220), 220) });
        followWords(text);
      } else {
        opts.onCaption?.({ who: "admin", text: clean(text.slice(-160), 160) });
      }
    }
  } catch { /* flux interrompu */ }
  if (fromAdmin && (final || text)) {
    const href = navIntent(text);
    if (href && Date.now() - lastNavAt > 1500) navigateNow(href);
  }
  if (segs.size > 50) segs = new Map([...segs].slice(-20));
}

function stateOf(p) {
  return p?.attributes?.["lk.agent.state"] || null;
}

export function startSpeechSync(r, o = {}) {
  stopSpeechSync();
  room = r;
  opts = o;
  try { r.registerTextStreamHandler(TOPIC, onStream); unsubs.push(() => { try { r.unregisterTextStreamHandler?.(TOPIC); } catch { /* */ } }); }
  catch { /* déjà enregistré ou client ancien : sous-titres indisponibles */ }
  const onAttrs = (_changed, p) => { const s = stateOf(p); if (s && p.identity !== r.localParticipant?.identity) o.onState?.(s); };
  r.on("participantAttributesChanged", onAttrs);
  unsubs.push(() => r.off("participantAttributesChanged", onAttrs));
}

export function stopSpeechSync() {
  while (unsubs.length) unsubs.pop()();
  room = null;
  segs = new Map();
  lastPointed = null;
}

export const __speech = { navIntent, followWords, onStream: (r, p, rm) => { room = rm; return onStream(r, p); },
                          setOpts: (o) => { opts = o; } };   // tests
