// Noms de fichiers lisibles pour tous les téléchargements ConstruPilot.
// Règle identique au backend (backend/engines/nom_fichier.py) :
//   ConstruPilot_<Type>[_<Numéro>]_<Sujet>[_<ref>]_<AAAA-MM-JJ>.<ext>
// Le serveur envoie ce nom dans Content-Disposition ; quand on télécharge un blob, on le relit ici.

const SPECIAUX = { "œ": "oe", "Œ": "OE", "æ": "ae", "Æ": "AE", "ß": "ss", "ø": "o", "Ø": "O", "’": "-", "'": "-", "°": "", "²": "2", "³": "3", "€": "EUR", "&": "et", "+": "-" };

export function slugPart(text, maxLen = 60) {
  let s = Array.from(String(text ?? "")).map((c) => SPECIAUX[c] ?? c).join("");
  s = s.normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/[^A-Za-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  if (maxLen && s.length > maxLen) {
    s = s.slice(0, maxLen).replace(/-+$/, "");
    const cut = s.lastIndexOf("-");
    if (cut >= maxLen * 0.6) s = s.slice(0, cut);
  }
  return s;
}

const OPAQUE = /^(?:[0-9a-f]{12,}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[a-z]{1,8}_(?=[0-9a-f]*[a-f])[0-9a-f]{8,})$/i;

export function isOpaque(text) {
  const s = String(text ?? "").trim();
  return !s || OPAQUE.test(s) || s.startsWith("file_");
}

function isoDate(value) {
  if (value) {
    const m = String(value).match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (m) return `${m[1]}-${m[2]}-${m[3]}`;
    const d = new Date(value);
    if (!Number.isNaN(d.getTime())) return d.toISOString().slice(0, 10);
  }
  return new Date().toISOString().slice(0, 10);
}

/** Nom lisible construit côté navigateur (fichiers générés localement, ou repli si l'en-tête manque). */
export function nomDocument(typeDoc, sujet, { ext = "pdf", date, ref, numero } = {}) {
  let t = slugPart(typeDoc, 40) || "Document";
  t = t.charAt(0).toUpperCase() + t.slice(1);
  const parts = ["ConstruPilot", t];
  const seen = new Set([t.toLowerCase()]);
  [[numero, 40, false], [sujet, 60, true], [ref, 30, true]].forEach(([v, max, checkOpaque]) => {
    if (v == null || (checkOpaque && isOpaque(v))) return;
    const p = slugPart(v, max);
    if (!p || seen.has(p.toLowerCase()) || p.toLowerCase() === "construpilot") return;
    parts.push(p);
    seen.add(p.toLowerCase());
  });
  if (date !== false) parts.push(isoDate(date));
  const e = String(ext || "").replace(/[^A-Za-z0-9]/g, "").toLowerCase();
  return parts.join("_") + (e ? `.${e}` : "");
}

/** Extrait le nom de fichier d'un en-tête Content-Disposition (filename* RFC 5987 prioritaire). */
export function filenameFromDisposition(header) {
  if (!header) return null;
  const star = /filename\*\s*=\s*([^']*)'[^']*'([^;]+)/i.exec(header);
  if (star) {
    try {
      return decodeURIComponent(star[2].trim().replace(/^"|"$/g, ""));
    } catch {
      /* encodage invalide : on tente filename= */
    }
  }
  const plain = /filename\s*=\s*("([^"]*)"|[^;]+)/i.exec(header);
  const name = plain ? (plain[2] ?? plain[1]).trim() : "";
  return name || null;
}

function headerOf(res) {
  const h = res?.headers;
  if (!h) return null;
  if (typeof h.get === "function") return h.get("content-disposition");
  return h["content-disposition"] || h["Content-Disposition"] || null;
}

/** Nom du fichier envoyé par le serveur (fetch Response ou réponse axios), sinon `fallback`. */
export function filenameFromResponse(res, fallback) {
  return filenameFromDisposition(headerOf(res)) || (fallback === undefined ? "ConstruPilot_document.pdf" : fallback);
}

/** Déclenche le téléchargement d'un blob sous un nom donné. */
export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}
