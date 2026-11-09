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

// ------------------------------------------------------------------ « cala-te » : silence immédiat (Lot 44)
const HUSH = /^\W*(?:(?:por favor|s'il te pla[iî]t|s'il vous pla[iî]t|please|aurora|ok|okay|bon|agora|maintenant|now|ya|vale)\W+)*(?:cala(?:-te| te|-se| se)?|calada|chiu+|psiu+|sil[eê]ncio|p[aá]ra(?: de falar| j[aá])?|basta|chega|tais[- ]toi|taisez[- ]vous|chut+|silence|arr[eê]te(?:z)?(?: de parler)?|stop(?: talking)?|shut up|be quiet|quiet|hush|c[aá]llate|silencio|basta ya|zitto|stai zitto|ruhe|sei still)\b\W*(?:por favor|s'il te pla[iî]t|please|aurora)?\W*$/i;
export const isHush = (t) => { const x = String(t || "").trim(); return !!x && x.length <= 60 && HUSH.test(x); };
// « Desligar Aurora », « desliga-te », « fecha a Aurora », « éteins-toi », « turn off Aurora »… : l'avatar se ferme.
// Un verbe d'arrêt seul ne suffit que sous sa forme pronominale (desliga-te, éteins-toi) ; sinon le nom (Aurora / avatar /
// assistente) est exigé, pour ne jamais fermer sur « desliga a luz ». Vérifié sur la phrase FINALE uniquement.
const OFF_VERB = String.raw`(?:deslig(?:a|ar|ue)|fech(?:a|ar|e)|encerr(?:a|ar|e)|termin(?:a|ar|e)|adeus|tchau|at[eé] logo|`
  + String.raw`[eé]tein(?:s|dre|t)|ferm(?:e|er)|au revoir|coupe(?:r)?|turn off|switch off|shut down|close|goodbye|bye|`
  + String.raw`apag(?:a|ar|ue)|cierr(?:a|e)|cerrar|adi[oó]s|spegni|chiudi|ciao|tsch[uü]ss)`;
const OFF_NAME = String.raw`(?:(?:a|à|la|l'|o|the|el|o meu|mon|ma)\s+|l')?(?:aurora|avatar|assistente|assistante|assistant|asistente)`;
const OFF_POLITE = String.raw`(?:por favor|s'il te pla[iî]t|s'il vous pla[iî]t|please|ok|okay|bon|agora|j[aá]|maintenant|now|pronto|obrigad[oa]|merci|thanks?|gracias)`;
const OFF_SELF = String.raw`(?:deslig(?:a|ue)[- ](?:te|se)|[eé]teins[- ]toi|[eé]teignez[- ]vous|ap[aá]gate|turn yourself off|switch yourself off)`;
const OFF = new RegExp(String.raw`^\W*(?:${OFF_POLITE}\W+)*(?:`
  + String.raw`${OFF_VERB}(?:[- ]?(?:la|-a|-o))?\W+${OFF_NAME}`          // « desligar (a) Aurora », « ferme Aurora »
  + String.raw`|${OFF_NAME}\W+${OFF_VERB}`                              // « Aurora, desliga »
  + String.raw`|(?:${OFF_NAME}\W+)?${OFF_SELF}`                         // « desliga-te », « éteins-toi »
  + String.raw`)(?:\W+${OFF_POLITE})*\W*$`, "i");
export const isOff = (t) => { const x = String(t || "").trim(); return !!x && x.length <= 70 && OFF.test(x); };

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
  let hushed = false;
  try {
    for await (const chunk of reader) {
      text += chunk;
      segs.set(seg, text);
      if (!fromAdmin) {
        opts.onCaption?.({ who: "agent", text: clean(text.slice(-220), 220) });
        followWords(text);
      } else {
        opts.onCaption?.({ who: "admin", text: clean(text.slice(-160), 160) });
        if (isHush(text)) { if (!hushed) { hushed = true; opts.onHush?.(); } }
        else if (text.trim().length > 3) opts.onSpeak?.();   // l'admin lui reparle : elle peut répondre
      }
    }
  } catch { /* flux interrompu */ }
  if (fromAdmin && final && isOff(text)) { opts.onOff?.(); return; }
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

export const __speech = { isHush, isOff, navIntent, followWords, onStream: (r, p, rm) => { room = rm; return onStream(r, p); },
                          setOpts: (o) => { opts = o; } };   // tests
