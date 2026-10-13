import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ExternalLink, Copy, Trash2, Upload, Globe, FileText } from "lucide-react";

const BASE = process.env.REACT_APP_BACKEND_URL;

const DOC_LAYOUTS = [
  { key: "bandeau", name: "Bandeau", desc: "Bandeau de couleur avec votre logo — le plus visible" },
  { key: "classique", name: "Classique", desc: "Logo à gauche, coordonnées à droite, filet de couleur — sobre" },
  { key: "compact", name: "Compact", desc: "Tableau dense, en-tête sur une ligne — tient sur une page" },
  { key: "essentiel", name: "Essentiel", desc: "En-tête papier à lettre, n° et date à droite — épuré" },
  { key: "detaille", name: "Détaillé par lots", desc: "Papier à lettre + sous-totaux par lot mis en avant" },
  { key: "signature", name: "Signature", desc: "En-tête sur bandeau doux, intitulé du projet en avant" },
];

const LETTERHEAD = ["essentiel", "detaille", "signature"];

const DOC_COLORS = [
  { key: "vert", name: "Vert bâtiment", hex: "#15803D" },
  { key: "sapin", name: "Vert sapin", hex: "#166534" },
  { key: "olive", name: "Olive", hex: "#4D7C0F" },
  { key: "ardoise", name: "Ardoise", hex: "#334155" },
  { key: "bleu", name: "Bleu profond", hex: "#1D4ED8" },
  { key: "sarcelle", name: "Sarcelle", hex: "#0F766E" },
  { key: "brique", name: "Brique", hex: "#B45309" },
  { key: "bordeaux", name: "Bordeaux", hex: "#9F1239" },
  { key: "graphite", name: "Graphite", hex: "#1F2937" },
];

/** Assombrit une couleur hex (même dérivation que la palette PDF côté backend). */
const shade = (hex, ratio) => {
  const h = (hex || "#15803D").replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
  const mix = (c) => Math.round(c * (1 - ratio));
  return `rgb(${mix(r)}, ${mix(g)}, ${mix(b)})`;
};

/** Éclaircit une couleur hex vers le blanc (fond doux du modèle « Signature »). */
const tint = (hex, ratio) => {
  const h = (hex || "#15803D").replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
  const mix = (c) => Math.round(c + (255 - c) * ratio);
  return `rgb(${mix(r)}, ${mix(g)}, ${mix(b)})`;
};

export default function CompanyPage() {
  const [page, setPage] = useState(null);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);

  const load = () => api.get("/company/page").then(({ data }) => { setPage(data); setForm({
    header_text: data.header_text || "", footer_text: data.footer_text || "", accent_color: data.accent_color || "#15803D", doc_layout: data.doc_layout || "bandeau", tagline: data.tagline || "",
    description: data.description || "", slug: data.slug || "", contact_phone: data.phone || "", website: data.website || "", show_reviews: data.show_reviews !== false,
  }); }).catch((e) => toast.error(e?.response?.data?.detail || "Chargement impossible"));
  useEffect(() => { load(); }, []);

  const save = async (extra = {}) => {
    setSaving(true);
    try {
      const { data } = await api.put("/company/page", { ...form, ...extra });
      setPage(data);
      toast.success(extra.published === true ? "Page publiée" : extra.published === false ? "Page dépubliée" : "Enregistré");
    } catch (e) { toast.error(e?.response?.data?.detail || "Enregistrement impossible"); }
    finally { setSaving(false); }
  };

  const addPhotos = async (files) => {
    setUploading(true);
    for (const f of Array.from(files || [])) {
      const fd = new FormData(); fd.append("file", f); fd.append("title", f.name.replace(/\.[^.]+$/, "").slice(0, 80));
      try { await api.post("/company/page/photos", fd, { headers: { "Content-Type": "multipart/form-data" } }); }
      catch (e) { toast.error(e?.response?.data?.detail || `Photo « ${f.name} » refusée`); }
    }
    setUploading(false); load();
  };
  const updPhoto = async (id, patch) => { try { await api.patch(`/company/page/photos/${id}`, patch); } catch { toast.error("Modification impossible"); } };
  const delPhoto = async (id) => { try { await api.delete(`/company/page/photos/${id}`); load(); } catch { toast.error("Suppression impossible"); } };

  if (!page) return <div className="p-8 text-sm text-muted-foreground" data-testid="company-page-loading">Chargement…</div>;
  const publicUrl = `${window.location.origin}/entreprise/${page.slug}`;
  const f = (k) => (e) => setForm((s) => ({ ...s, [k]: e.target.value }));

  return (
    <div className="max-w-5xl mx-auto p-4 md:p-8 space-y-8" data-testid="company-page">
      <header>
        <h1 className="text-2xl md:text-3xl font-semibold">Ma page & mes documents</h1>
        <p className="text-sm text-muted-foreground">Personnalisez vos devis et factures, et présentez votre entreprise à vos clients comme un site.</p>
      </header>

      <section className="grid lg:grid-cols-2 gap-6">
        <div className="rounded-xl border p-5 space-y-3" data-testid="pdf-custom-form">
          <h2 className="font-semibold flex items-center gap-2"><FileText className="h-4 w-4" /> Devis, factures et avoirs</h2>
          <label className="block text-sm">Pied de page (mentions légales, garanties, RIB…)
            <textarea data-testid="pdf-footer-input" className="mt-1 w-full rounded-md border bg-background p-2 text-sm min-h-[80px]" maxLength={600} value={form.footer_text} onChange={f("footer_text")} placeholder="Ex : SARL au capital de 10 000 € — RCS Paris 123 456 789 — Assurance décennale AXA n° … — Pénalités de retard : 3 × taux légal" />
          </label>
          <div className="space-y-2" data-testid="pdf-layout-picker">
            <p className="text-sm">Modèle de mise en page
              <span className="block text-xs text-muted-foreground">S'applique aux devis, factures et avoirs.</span>
            </p>
            <div className="grid sm:grid-cols-3 gap-2">
              {DOC_LAYOUTS.map((l) => {
                const active = form.doc_layout === l.key;
                return (
                  <button key={l.key} type="button" onClick={() => setForm((st) => ({ ...st, doc_layout: l.key }))}
                          data-testid={`pdf-layout-${l.key}`}
                          className={`text-left rounded-md border p-2.5 transition-colors ${active ? "border-foreground bg-muted/60" : "hover:bg-muted/30"}`}>
                    <span className="block h-8 rounded-sm mb-2 overflow-hidden flex items-center"
                          style={l.key === "bandeau"
                            ? { background: shade(form.accent_color, 0.22) }
                            : l.key === "signature"
                            ? { background: tint(form.accent_color, 0.88), borderBottom: `3px solid ${form.accent_color}` }
                            : { borderBottom: `3px solid ${form.accent_color}`, background: l.key === "compact" ? "#f6f6f4" : "transparent" }}>
                      <span className="h-4 w-4 ml-1.5 rounded-sm bg-white/90 border" />
                    </span>
                    <span className="block text-xs font-semibold">{l.name}</span>
                    <span className="block text-[10px] text-muted-foreground leading-snug">{l.desc}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="space-y-2" data-testid="pdf-color-picker">
            <p className="text-sm">Couleur des documents
              <span className="block text-xs text-muted-foreground">Toute la palette du devis en découle : bandeau, titres, tableau, total et filets.</span>
            </p>
            <div className="flex flex-wrap gap-2">
              {DOC_COLORS.map((c) => (
                <button key={c.hex} type="button" onClick={() => setForm((st) => ({ ...st, accent_color: c.hex }))}
                        title={c.name} aria-label={c.name}
                        data-testid={`pdf-color-${c.key}`}
                        className={`h-8 w-8 rounded-full border-2 transition-transform hover:scale-110 ${form.accent_color?.toUpperCase() === c.hex ? "border-foreground scale-110" : "border-transparent"}`}
                        style={{ background: c.hex }} />
              ))}
              <label className="flex items-center gap-2 text-xs text-muted-foreground ml-1">
                <input type="color" data-testid="pdf-accent-input" value={form.accent_color} onChange={f("accent_color")} className="h-8 w-10 rounded border cursor-pointer" />
                {form.accent_color}
              </label>
            </div>
          </div>
          <Button onClick={() => save()} disabled={saving} data-testid="pdf-custom-save-btn" className="rounded-sm">Enregistrer</Button>
        </div>
        <div className="rounded-xl border p-5 bg-white text-slate-900 text-xs space-y-3" data-testid="pdf-preview" aria-label="Aperçu du document">
          {form.doc_layout === "bandeau" ? (
            <div className="flex items-center gap-3 p-3 -m-2 rounded-t" style={{ background: shade(form.accent_color, 0.22) }} data-testid="pdf-preview-banner">
              {page.has_logo && <img src={`${BASE}/api/branding/${page.user_id}/logo`} alt="" className="h-10 w-10 object-contain bg-white rounded p-0.5" />}
              <div className="text-white min-w-0">
                <div className="font-bold text-sm truncate">{page.company_name}</div>
                <div className="opacity-90 truncate">{page.contact_line}</div>
              </div>
            </div>
          ) : form.doc_layout === "classique" ? (
            <div className="flex items-start justify-between gap-3 pb-2" style={{ borderBottom: `2px solid ${form.accent_color}` }} data-testid="pdf-preview-banner">
              {page.has_logo && <img src={`${BASE}/api/branding/${page.user_id}/logo`} alt="" className="h-10 w-10 object-contain" />}
              <div className="text-right min-w-0">
                <div className="font-bold text-sm truncate">{page.company_name}</div>
                <div className="text-slate-500 truncate">{page.contact_line}</div>
              </div>
            </div>
          ) : LETTERHEAD.includes(form.doc_layout) ? (
            <div className="flex items-start justify-between gap-3 pb-2"
                 style={form.doc_layout === "signature"
                   ? { background: tint(form.accent_color, 0.9), padding: "8px", borderRadius: 4, border: `1px solid ${tint(form.accent_color, 0.6)}` }
                   : { borderBottom: `2px solid ${form.accent_color}` }}
                 data-testid="pdf-preview-banner">
              <div className="flex items-center gap-2 min-w-0">
                {page.has_logo && <img src={`${BASE}/api/branding/${page.user_id}/logo`} alt="" className="h-9 w-9 object-contain" />}
                <div className="min-w-0">
                  <div className="font-bold text-sm truncate" style={{ color: shade(form.accent_color, 0.45) }}>{page.company_name}</div>
                  <div className="text-slate-500 truncate">{page.contact_line}</div>
                </div>
              </div>
              <div className="text-right shrink-0">
                <div className="font-bold text-base leading-tight" style={{ color: shade(form.accent_color, 0.45) }}>DEVIS</div>
                <div className="text-slate-500 text-[10px]">N° DEV-2026-0001</div>
              </div>
            </div>
          ) : (
            <div className="rounded-sm border px-2 py-1.5 text-[10px] truncate" style={{ borderColor: form.accent_color, background: "#f8faf9" }} data-testid="pdf-preview-banner">
              <b>{page.company_name}</b> · {page.contact_line}
            </div>
          )}
          {form.doc_layout === "signature" && <p className="text-[10px] uppercase tracking-wide" style={{ color: form.accent_color }} data-testid="pdf-preview-project">Votre projet</p>}
          <p className="whitespace-pre-wrap text-slate-600 italic text-slate-400" data-testid="pdf-preview-hint">Votre logo et vos coordonnées apparaissent dans le bandeau ci-dessus et vos mentions légales dans le pied de page.</p>
          <h3 className="text-lg font-semibold" style={{ color: form.accent_color }}>Devis n° DEV-2026-0001</h3>
          <table className="w-full">
            <thead><tr style={{ background: shade(form.accent_color, 0.22), color: "#fff" }}>
              <th className="text-left py-1 px-2 font-semibold">Désignation</th><th className="text-right py-1 px-2 font-semibold">Total HT</th>
            </tr></thead>
            <tbody>
            <tr className="border-b"><td className="py-1">Dépose et repose de cloison</td><td className="text-right">1 250,00 €</td></tr>
            <tr className="border-b"><td className="py-1">Enduit et peinture</td><td className="text-right">840,00 €</td></tr>
            <tr style={{ background: form.accent_color, color: "#fff" }}><td className="py-1.5 px-2 font-semibold">Total TTC</td><td className="text-right px-2 font-semibold">2 299,00 €</td></tr>
          </tbody></table>
          <p className="whitespace-pre-wrap text-slate-500 border-t pt-2" data-testid="pdf-preview-footer">{form.footer_text || <span className="italic text-slate-400">Votre pied de page apparaîtra ici</span>}</p>
        </div>
      </section>

      <section className="rounded-xl border p-5 space-y-4" data-testid="public-page-form">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-semibold flex items-center gap-2"><Globe className="h-4 w-4" /> Ma page entreprise (site vitrine)</h2>
          <div className="flex items-center gap-2">
            <span className={`text-xs px-2 py-1 rounded ${page.published ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-600"}`} data-testid="public-page-status">{page.published ? "Publiée" : "Non publiée"}</span>
            <Button variant={page.published ? "outline" : "default"} className="rounded-sm" disabled={saving} onClick={() => save({ published: !page.published })} data-testid="public-page-publish-btn">
              {page.published ? "Dépublier" : "Publier ma page"}
            </Button>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted-foreground">{window.location.origin}/entreprise/</span>
          <Input data-testid="public-slug-input" value={form.slug} onChange={f("slug")} className="h-8 w-56 rounded-sm" />
          <Button size="sm" variant="ghost" onClick={() => { navigator.clipboard?.writeText(publicUrl); toast.success("Lien copié"); }} data-testid="public-copy-link-btn"><Copy className="h-4 w-4" /></Button>
          <a href={publicUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary underline text-xs" data-testid="public-open-link">Voir ma page <ExternalLink className="h-3 w-3" /></a>
        </div>
        <div className="grid md:grid-cols-2 gap-3">
          <label className="text-sm">Accroche<Input data-testid="public-tagline-input" value={form.tagline} onChange={f("tagline")} maxLength={140} className="mt-1 rounded-sm" placeholder="Rénovation complète et gros œuvre depuis 1998" /></label>
          <label className="text-sm">Téléphone affiché<Input data-testid="public-phone-input" value={form.contact_phone} onChange={f("contact_phone")} className="mt-1 rounded-sm" /></label>
          <label className="text-sm md:col-span-2">Présentation<textarea data-testid="public-description-input" className="mt-1 w-full rounded-md border bg-background p-2 text-sm min-h-[90px]" maxLength={2000} value={form.description} onChange={f("description")} /></label>
          <label className="text-sm">Site web<Input data-testid="public-website-input" value={form.website} onChange={f("website")} className="mt-1 rounded-sm" placeholder="https://" /></label>
          <label className="text-sm flex items-center gap-2 mt-6"><input type="checkbox" checked={form.show_reviews} onChange={(e) => setForm((s) => ({ ...s, show_reviews: e.target.checked }))} data-testid="public-reviews-toggle" /> Afficher mes avis clients</label>
        </div>
        <Button onClick={() => save()} disabled={saving} data-testid="public-page-save-btn" className="rounded-sm">Enregistrer la page</Button>
      </section>

      <section className="rounded-xl border p-5 space-y-4" data-testid="showcase-section">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-semibold">Chantiers réalisés ({page.photos.length}/24)</h2>
          <input ref={fileRef} type="file" accept="image/*" multiple className="hidden" onChange={(e) => { addPhotos(e.target.files); e.target.value = ""; }} data-testid="showcase-file-input" />
          <Button variant="outline" className="rounded-sm gap-2" disabled={uploading} onClick={() => fileRef.current?.click()} data-testid="showcase-add-btn"><Upload className="h-4 w-4" /> {uploading ? "Envoi…" : "Ajouter des photos"}</Button>
        </div>
        {page.photos.length === 0 && <p className="text-sm text-muted-foreground">Ajoutez vos plus belles réalisations : elles apparaîtront sur votre page publique avec un titre et une description.</p>}
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {page.photos.map((p) => (
            <figure key={p.photo_id} className="rounded-lg border overflow-hidden" data-testid={`showcase-photo-${p.photo_id}`}>
              <img src={`${BASE}/api/company/page/photo/${p.photo_id}`} alt={p.title || "Chantier réalisé"} className="w-full h-40 object-cover" />
              <figcaption className="p-2 space-y-1">
                <Input defaultValue={p.title} placeholder="Titre du chantier" className="h-8 rounded-sm text-sm" onBlur={(e) => updPhoto(p.photo_id, { title: e.target.value })} data-testid={`showcase-title-${p.photo_id}`} />
                <textarea defaultValue={p.description} placeholder="Description (travaux réalisés, lieu, durée…)" className="w-full rounded-md border bg-background p-2 text-xs min-h-[48px]" onBlur={(e) => updPhoto(p.photo_id, { description: e.target.value })} data-testid={`showcase-desc-${p.photo_id}`} />
                <button type="button" className="text-xs text-red-600 inline-flex items-center gap-1" onClick={() => delPhoto(p.photo_id)} data-testid={`showcase-del-${p.photo_id}`}><Trash2 className="h-3 w-3" /> Retirer</button>
              </figcaption>
            </figure>
          ))}
        </div>
      </section>
    </div>
  );
}
