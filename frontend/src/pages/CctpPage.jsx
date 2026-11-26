import { useEffect, useMemo, useRef, useState } from "react";
import {
  ScrollText, Loader2, Download, FileText, FileSpreadsheet, Plus, Trash2, ShieldCheck, Sparkles, Archive, ChevronDown, ChevronRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { filenameFromResponse } from "@/lib/downloadName";

const UNITES = ["m2", "ml", "m3", "u", "ens", "forfait"];
const EMPTY_PROJET = {
  nom: "", adresse: "", maitre_ouvrage: "", maitre_oeuvre: "", nature: "neuf", description: "", indice: "A", style: "economiste",
  tce: true, delai: "", intervenants: { architecte: "", bet_structure: "", bet_fluides: "", bet_thermique: "", coordonnateur_sps: "", controleur_technique: "" },
  consultation: { date_limite: "", remise: "", visite: "", validite_jours: 90, variantes: true },
};
const INTERVENANTS = [["architecte", "Architecte"], ["bet_structure", "BET Structure"], ["bet_fluides", "BET Fluides"],
  ["bet_thermique", "BET Thermique"], ["coordonnateur_sps", "Coordonnateur SPS"], ["controleur_technique", "Contrôleur technique"]];
const TYPES_PIECE = [["", "Type auto"], ["sejour", "Séjour"], ["cuisine", "Cuisine"], ["chambre", "Chambre"], ["bureau", "Bureau"],
  ["sdb", "Salle de bain / d'eau"], ["wc", "WC"], ["entree", "Entrée"], ["circulation", "Circulation"], ["buanderie", "Buanderie / cellier"],
  ["garage", "Garage"], ["exterieur", "Extérieur"], ["autre", "Autre"]];
// Modèle « maison individuelle » (organisation type d'un DCE d'architecte : élec / CVC-plomberie / aménagements intérieurs)
const PRESET_MAISON = {
  gros_oeuvre: { code: "gros_oeuvre", numero: 1, titre: "", inclure: [], ouvrages: [], lignes: [], notes: "" },
  charpente_couverture: { code: "charpente_couverture", numero: 2, titre: "", inclure: [], ouvrages: [], lignes: [], notes: "" },
  menuiseries_ext: { code: "menuiseries_ext", numero: 3, titre: "", inclure: [], ouvrages: [], lignes: [], notes: "" },
  electricite: { code: "electricite", numero: 4, titre: "", inclure: [], ouvrages: ["chantier_elec", "branchement", "terre"], lignes: [], notes: "" },
  cvc: { code: "cvc", numero: 5, titre: "CVC – Plomberie", inclure: ["plomberie"], ouvrages: ["pac_air_eau", "plancher_chauffant", "vmc", "distribution", "evacuations", "ecs"], lignes: [], notes: "" },
  platrerie: { code: "platrerie", numero: 6, titre: "Aménagements intérieurs", inclure: ["menuiseries_int", "peinture", "sols_durs", "sols_souples"], ouvrages: [], lignes: [], notes: "" },
};
const PIECES_MAISON = [
  ["Entrée", "RDC"], ["Séjour", "RDC"], ["Cuisine", "RDC"], ["WC", "RDC"], ["Buanderie", "RDC"], ["Garage", "RDC"],
  ["Chambre 1", "R+1"], ["Chambre 2", "R+1"], ["Chambre 3", "R+1"], ["Salle de bain 1", "R+1"], ["Salle de bain 2", "R+1"], ["Dégagement", "R+1"],
].map(([nom, niveau]) => ({ nom, type: "", surface: null, niveau, extras: [] }));

async function download(url, fallback) {
  try {
    const resp = await api.get(url, { responseType: "blob" });
    const href = URL.createObjectURL(resp.data);
    const a = document.createElement("a");
    a.href = href; a.download = filenameFromResponse(resp, fallback); a.click();
    URL.revokeObjectURL(href);
  } catch { toast.error("Téléchargement impossible"); }
}

function LotCard({ lot, sel, onChange, catalogue, absorbe }) {
  const [open, setOpen] = useState(false);
  const active = !!sel;
  const toggle = (v) => onChange(v ? { code: lot.code, numero: lot.numero, titre: "", inclure: [], ouvrages: [], lignes: [], notes: "" } : null);
  if (absorbe) {
    return (
      <div className="surface p-4 rounded-xl opacity-60 text-sm" data-testid={`cctp-lot-${lot.code}`}>
        <span className="text-xs text-muted-foreground">Lot {String(lot.numero).padStart(2, "0")}</span>
        <p className="font-semibold leading-tight">{lot.titre}</p>
        <p className="text-xs mt-1">Regroupé dans « {absorbe} »</p>
      </div>
    );
  }
  const inclus = (sel?.inclure || []).map((c) => catalogue.find((l) => l.code === c)).filter(Boolean);
  const ouvragesVisibles = [lot, ...inclus].flatMap((l) => l.ouvrages);
  const upd = (patch) => onChange({ ...sel, ...patch });
  const setLigne = (i, patch) => upd({ lignes: sel.lignes.map((l, j) => (j === i ? { ...l, ...patch } : l)) });
  return (
    <div className={`surface p-4 rounded-xl border ${active ? "border-primary/60" : "border-transparent"}`} data-testid={`cctp-lot-${lot.code}`}>
      <div className="flex items-center gap-3">
        <Checkbox checked={active} onCheckedChange={(v) => { toggle(!!v); if (v) setOpen(true); }} />
        <button type="button" className="flex-1 text-left" onClick={() => active && setOpen(!open)}>
          <span className="text-xs text-muted-foreground">Lot {String(sel?.numero ?? lot.numero).padStart(2, "0")}</span>
          <p className="font-semibold leading-tight">{sel?.titre || lot.titre}</p>
          {inclus.length > 0 && <p className="text-xs text-primary">+ {inclus.map((l) => l.titre.split(" – ")[0]).join(", ")}</p>}
        </button>
        {active && (open ? <ChevronDown size={18} /> : <ChevronRight size={18} />)}
      </div>
      {active && open && (
        <div className="mt-4 space-y-4">
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">N° de lot</span>
            <Input type="number" min={1} max={99} className="w-20 h-8" value={sel.numero}
              onChange={(e) => upd({ numero: Number(e.target.value) || lot.numero })} />
            <Input className="h-8 flex-1" placeholder={`Intitulé (défaut : ${lot.titre})`} value={sel.titre || ""}
              onChange={(e) => upd({ titre: e.target.value })} />
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Regrouper dans ce lot</p>
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              {catalogue.filter((l) => l.code !== lot.code).map((l) => (
                <label key={l.code} className="flex items-center gap-1.5 text-xs cursor-pointer">
                  <Checkbox checked={(sel.inclure || []).includes(l.code)} onCheckedChange={(v) =>
                    upd({ inclure: v ? [...(sel.inclure || []), l.code] : (sel.inclure || []).filter((c) => c !== l.code) })} />
                  {l.titre.split(" – ")[0]}
                </label>
              ))}
            </div>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Ouvrages types (laisser vide = tous)</p>
            <div className="grid sm:grid-cols-2 gap-2">
              {ouvragesVisibles.map((o) => (
                <label key={o.code} className="flex items-start gap-2 text-sm cursor-pointer">
                  <Checkbox checked={sel.ouvrages.includes(o.code)} onCheckedChange={(v) =>
                    upd({ ouvrages: v ? [...sel.ouvrages, o.code] : sel.ouvrages.filter((c) => c !== o.code) })} />
                  <span>{o.titre.charAt(0) + o.titre.slice(1).toLowerCase()} <span className="text-muted-foreground">({o.unite})</span></span>
                </label>
              ))}
            </div>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Ouvrages et quantités du projet</p>
            {sel.lignes.map((l, i) => (
              <div key={i} className="grid grid-cols-12 gap-2 mb-2">
                <Input className="col-span-12 sm:col-span-5 h-9" placeholder="Désignation (ex. Cloison 72/48 BA13)" value={l.designation}
                  onChange={(e) => setLigne(i, { designation: e.target.value })} />
                <select className="col-span-3 sm:col-span-1 h-9 rounded-md border bg-background px-1 text-sm" value={l.unite}
                  onChange={(e) => setLigne(i, { unite: e.target.value })}>
                  {UNITES.map((u) => <option key={u}>{u}</option>)}
                </select>
                <Input className="col-span-3 sm:col-span-2 h-9" type="number" min={0} step="0.01" placeholder="Qté" value={l.quantite ?? ""}
                  onChange={(e) => setLigne(i, { quantite: e.target.value === "" ? null : Number(e.target.value) })} />
                <Input className="col-span-5 sm:col-span-3 h-9" placeholder="Localisation" value={l.localisation}
                  onChange={(e) => setLigne(i, { localisation: e.target.value })} />
                <Button variant="ghost" size="icon" className="col-span-1 h-9" onClick={() => upd({ lignes: sel.lignes.filter((_, j) => j !== i) })}>
                  <Trash2 size={16} />
                </Button>
              </div>
            ))}
            <Button variant="outline" size="sm" onClick={() => upd({ lignes: [...sel.lignes, { designation: "", unite: "m2", quantite: null, localisation: "" }] })}>
              <Plus size={15} className="me-1" /> Ajouter un ouvrage
            </Button>
          </div>
          <Textarea rows={2} placeholder="Consignes pour ce lot (matériaux imposés, performances, site occupé…)" value={sel.notes}
            onChange={(e) => upd({ notes: e.target.value })} />
          <p className="text-xs text-muted-foreground">Références : {lot.refs.map((r) => r.split(" — ")[0]).join(" · ")}</p>
        </div>
      )}
    </div>
  );
}

export default function CctpPage() {
  const [catalogue, setCatalogue] = useState([]);
  const [devis, setDevis] = useState([]);
  const [projet, setProjet] = useState(EMPTY_PROJET);
  const [docId, setDocId] = useState("");
  const [sel, setSel] = useState({});
  const [ia, setIa] = useState(true);
  const [dossier, setDossier] = useState(null);
  const [busy, setBusy] = useState(false);
  const [historique, setHistorique] = useState([]);
  const timer = useRef(null);

  const loadHistory = () => api.get("/pro/cctp/dossiers").then((r) => setHistorique(r.data.dossiers || [])).catch(() => {});
  useEffect(() => {
    api.get("/pro/cctp/catalogue").then((r) => setCatalogue(r.data.lots || [])).catch(() => toast.error("Catalogue CCTP indisponible"));
    api.get("/documents", { params: { doc_type: "quote" } }).then((r) => setDevis(r.data.documents || [])).catch(() => {});
    loadHistory();
    return () => clearTimeout(timer.current);
  }, []);

  const nbLots = useMemo(() => Object.values(sel).filter(Boolean).length, [sel]);
  const setP = (k) => (e) => setProjet({ ...projet, [k]: e.target.value });
  const [pieces, setPieces] = useState([]);
  const [plans, setPlans] = useState("");
  const absorbes = useMemo(() => {
    const m = {};
    Object.values(sel).filter(Boolean).forEach((l) => (l.inclure || []).forEach((c) => {
      m[c] = l.titre || catalogue.find((x) => x.code === l.code)?.titre;
    }));
    return m;
  }, [sel, catalogue]);
  const setPiece = (i, patch) => setPieces(pieces.map((p, j) => (j === i ? { ...p, ...patch } : p)));
  const appliquerModele = () => {
    setSel(PRESET_MAISON);
    setProjet((p) => ({ ...p, style: "architecte", tce: true }));
    if (!pieces.length) setPieces(PIECES_MAISON);
    toast.success("Modèle maison individuelle appliqué : ajustez les lots et les pièces");
  };

  const poll = (id) => {
    api.get(`/pro/cctp/dossiers/${id}`).then((r) => {
      setDossier(r.data);
      if (r.data.status === "running") timer.current = setTimeout(() => poll(id), 2500);
      else {
        setBusy(false); loadHistory();
        if (r.data.status === "done") toast.success("CCTP rédigé");
        else toast.error(r.data.error || "Rédaction impossible");
      }
    }).catch(() => { setBusy(false); toast.error("Suivi impossible"); });
  };

  const generer = async () => {
    if (!projet.nom.trim()) return toast.error("Indiquez le nom du projet");
    if (!nbLots && !docId) return toast.error("Choisissez au moins un lot ou un devis");
    const lots = Object.entries(sel).filter(([code, l]) => l && !absorbes[code]).map(([, l]) => ({
      ...l, lignes: l.lignes.filter((x) => x.designation.trim()),
    }));
    const payload = {
      ...projet,
      pieces: pieces.filter((p) => p.nom.trim()).map((p) => ({ ...p, surface: p.surface || null })),
      plans: plans.split("\n").map((x) => x.trim()).filter(Boolean),
    };
    setBusy(true); setDossier(null);
    try {
      const r = await api.post("/pro/cctp/dossiers", { projet: payload, lots, doc_id: docId || null, ia });
      poll(r.data.dossier_id);
    } catch (e) {
      setBusy(false);
      toast.error(e?.response?.data?.detail || "Rédaction impossible");
    }
  };

  const fichiers = dossier?.fichiers || [];
  return (
    <div className="max-w-6xl mx-auto px-5 py-8 space-y-6" data-testid="cctp-page">
      <div>
        <p className="overline text-primary">Pièces écrites · DCE</p>
        <h1 className="font-display text-3xl sm:text-4xl font-bold flex items-center gap-3"><ScrollText /> Rédacteur CCTP</h1>
        <p className="text-sm text-muted-foreground mt-2 max-w-3xl">
          ConstruPilot rédige le CCTP de chaque lot au format économiste — page de garde à votre logo, prescriptions
          particulières, mise en œuvre selon les NF DTU, articles avec localisation — et le cadre de DPGF à la même
          numérotation, prêts à joindre au DCE.
        </p>
      </div>

      <section className="surface p-5 rounded-2xl space-y-3">
        <h2 className="font-semibold">1. Projet</h2>
        <div className="grid sm:grid-cols-2 gap-3">
          <Input placeholder="Nom du projet *" value={projet.nom} onChange={setP("nom")} data-testid="cctp-nom" />
          <Input placeholder="Adresse du chantier" value={projet.adresse} onChange={setP("adresse")} />
          <Input placeholder="Maître d'ouvrage" value={projet.maitre_ouvrage} onChange={setP("maitre_ouvrage")} />
          <Input placeholder="Maître d'œuvre" value={projet.maitre_oeuvre} onChange={setP("maitre_oeuvre")} />
        </div>
        <div className="flex flex-wrap items-center gap-4 text-sm">
          {[["neuf", "Construction neuve"], ["renovation", "Rénovation / réhabilitation"]].map(([v, l]) => (
            <label key={v} className="flex items-center gap-2 cursor-pointer">
              <input type="radio" name="nature" checked={projet.nature === v} onChange={() => setProjet({ ...projet, nature: v })} /> {l}
            </label>
          ))}
          <span className="flex items-center gap-2">Indice <Input className="w-16 h-8" value={projet.indice} onChange={setP("indice")} /></span>
        </div>
        <Textarea rows={3} placeholder="Description du projet (surface, niveaux, contraintes, performances visées…) — aide l'IA à adapter les articles"
          value={projet.description} onChange={setP("description")} />
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <span className="font-medium">Mise en forme :</span>
          {[["economiste", "Économiste (articles numérotés, localisation)"], ["architecte", "Architecte (généralités + descriptif, « Position »)"]].map(([v, l]) => (
            <label key={v} className="flex items-center gap-2 cursor-pointer">
              <input type="radio" name="style" checked={projet.style === v} onChange={() => setProjet({ ...projet, style: v })} /> {l}
            </label>
          ))}
        </div>
        <details className="text-sm">
          <summary className="cursor-pointer font-medium">Intervenants (page de garde et RC)</summary>
          <div className="grid sm:grid-cols-2 gap-3 mt-3">
            {INTERVENANTS.map(([k, l]) => (
              <Input key={k} placeholder={l} value={projet.intervenants[k]}
                onChange={(e) => setProjet({ ...projet, intervenants: { ...projet.intervenants, [k]: e.target.value } })} />
            ))}
          </div>
        </details>
      </section>

      <section className="surface p-5 rounded-2xl space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="font-semibold">Programme par pièce (facultatif)</h2>
          <Button variant="outline" size="sm" className="ms-auto" onClick={appliquerModele} data-testid="cctp-modele-maison">
            <Sparkles size={15} className="me-1" /> Modèle maison individuelle
          </Button>
        </div>
        <p className="text-sm text-muted-foreground">
          Les lots Électricité et Plomberie listent alors l'équipement de chaque pièce (socle NF C 15-100) et le DPGF est quantifié automatiquement.
        </p>
        {pieces.map((p, i) => (
          <div key={i} className="grid grid-cols-12 gap-2">
            <Input className="col-span-12 sm:col-span-4 h-9" placeholder="Pièce (ex. Chambre 1)" value={p.nom} onChange={(e) => setPiece(i, { nom: e.target.value })} />
            <select className="col-span-4 sm:col-span-2 h-9 rounded-md border bg-background px-1 text-sm" value={p.type} onChange={(e) => setPiece(i, { type: e.target.value })}>
              {TYPES_PIECE.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            <Input className="col-span-3 sm:col-span-1 h-9" type="number" min={0} placeholder="m²" value={p.surface ?? ""}
              onChange={(e) => setPiece(i, { surface: e.target.value === "" ? null : Number(e.target.value) })} />
            <Input className="col-span-4 sm:col-span-1 h-9" placeholder="Niveau" value={p.niveau} onChange={(e) => setPiece(i, { niveau: e.target.value })} />
            <Input className="col-span-11 sm:col-span-3 h-9" placeholder="Équipements en plus (séparés par ;)" value={(p.extras || []).join("; ")}
              onChange={(e) => setPiece(i, { extras: e.target.value.split(";").map((x) => x.trim()).filter(Boolean) })} />
            <Button variant="ghost" size="icon" className="col-span-1 h-9" onClick={() => setPieces(pieces.filter((_, j) => j !== i))}><Trash2 size={16} /></Button>
          </div>
        ))}
        <Button variant="outline" size="sm" onClick={() => setPieces([...pieces, { nom: "", type: "", surface: null, niveau: "", extras: [] }])}>
          <Plus size={15} className="me-1" /> Ajouter une pièce
        </Button>
      </section>

      <section className="surface p-5 rounded-2xl space-y-3">
        <h2 className="font-semibold">2. Partir d'un devis (facultatif)</h2>
        <p className="text-sm text-muted-foreground">Les lignes du devis sont rattachées aux lots et aux ouvrages types, avec leurs quantités.</p>
        <select className="h-10 w-full sm:w-2/3 rounded-md border bg-background px-3 text-sm" value={docId} onChange={(e) => setDocId(e.target.value)}
          data-testid="cctp-devis">
          <option value="">— Aucun devis —</option>
          {devis.map((d) => <option key={d.doc_id} value={d.doc_id}>{[d.number, d.title].filter(Boolean).join(" · ")}</option>)}
        </select>
      </section>

      <section className="space-y-3">
        <h2 className="font-semibold">3. Lots à rédiger {nbLots > 0 && <span className="text-primary">({nbLots})</span>}</h2>
        <div className="grid md:grid-cols-2 gap-3">
          {catalogue.map((lot) => (
            <LotCard key={lot.code} lot={lot} sel={sel[lot.code]} catalogue={catalogue} absorbe={absorbes[lot.code]}
              onChange={(v) => setSel({ ...sel, [lot.code]: v })} />
          ))}
        </div>
      </section>

      <section className="surface p-5 rounded-2xl space-y-3">
        <label className="flex items-center gap-3 text-sm font-semibold">
          <Switch checked={projet.tce} onCheckedChange={(v) => setProjet({ ...projet, tce: v })} />
          4. Pièces du DCE : page de garde & sommaire, règlement de consultation, clauses générales TCE
        </label>
        {projet.tce && (
          <div className="grid sm:grid-cols-2 gap-3">
            <Input placeholder="Date limite de remise des offres" value={projet.consultation.date_limite}
              onChange={(e) => setProjet({ ...projet, consultation: { ...projet.consultation, date_limite: e.target.value } })} />
            <Input placeholder="Délai d'exécution (ex. 8 mois, période de préparation comprise)" value={projet.delai} onChange={setP("delai")} />
            <Textarea rows={4} className="sm:col-span-2" placeholder={"Pièces graphiques jointes, une par ligne\nPlan masse\nPlan RDC 1/50\nPlan électricité RDC…"}
              value={plans} onChange={(e) => setPlans(e.target.value)} />
          </div>
        )}
      </section>

      <section className="surface p-5 rounded-2xl flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-3 text-sm">
          <Switch checked={ia} onCheckedChange={setIa} />
          <span><Sparkles size={14} className="inline me-1 text-primary" />Rédaction adaptée au projet par l'IA</span>
        </label>
        <span className="text-xs text-muted-foreground flex items-center gap-1">
          <ShieldCheck size={14} /> Normes vérifiées sur liste blanche · quantités jamais inventées
        </span>
        <Button className="ms-auto" onClick={generer} disabled={busy} data-testid="cctp-generer">
          {busy ? <Loader2 size={16} className="animate-spin me-2" /> : <ScrollText size={16} className="me-2" />}
          {busy ? "Rédaction en cours…" : "Rédiger le CCTP"}
        </Button>
      </section>

      {dossier && dossier.status === "done" && (
        <section className="surface p-5 rounded-2xl space-y-4" data-testid="cctp-resultat">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="font-semibold">Dossier prêt — {dossier.projet?.nom}</h2>
            <Button size="sm" className="ms-auto" onClick={() => download(`/pro/cctp/dossiers/${dossier.dossier_id}/zip`, "DCE.zip")}>
              <Archive size={15} className="me-1" /> Télécharger le DCE (.zip)
            </Button>
          </div>
          <div className="grid sm:grid-cols-2 gap-2">
            {fichiers.map((f) => (
              <button key={f.index} type="button" onClick={() => download(`/pro/cctp/dossiers/${dossier.dossier_id}/fichiers/${f.index}`, f.nom)}
                className="flex items-center gap-2 text-left text-sm p-3 rounded-lg border hover:border-primary">
                {f.nom.endsWith(".xlsx") ? <FileSpreadsheet size={17} className="text-primary" /> : <FileText size={17} className="text-primary" />}
                <span className="flex-1 truncate">{f.nom}</span><Download size={15} />
              </button>
            ))}
          </div>
          <div className="space-y-2">
            <h3 className="text-sm font-semibold">Points à vérifier par le rédacteur</h3>
            {(dossier.lots || []).map((l) => (
              <div key={l.code} className="text-sm">
                <p className="font-medium">Lot {String(l.numero).padStart(2, "0")} — {l.titre}
                  <span className="text-muted-foreground"> · {l.articles} articles · {l.lignes} lignes DPGF · {l.mode === "ia" ? "rédaction IA" : "articles types"}</span></p>
                <ul className="list-disc ms-5 text-muted-foreground">
                  {(l.points.length ? l.points : ["Aucun point signalé."]).map((p, i) => <li key={i}>{p}</li>)}
                </ul>
              </div>
            ))}
          </div>
        </section>
      )}

      {historique.length > 0 && (
        <section className="space-y-2">
          <h2 className="font-semibold">Dossiers récents</h2>
          {historique.map((d) => (
            <button key={d.dossier_id} type="button" className="w-full surface p-3 rounded-lg flex items-center gap-3 text-sm text-left"
              onClick={() => d.status === "done" ? setDossier(d) : poll(d.dossier_id)}>
              <ScrollText size={16} className="text-primary" />
              <span className="flex-1">{d.projet?.nom} · {(d.lots || []).length} lot(s)</span>
              <span className="text-muted-foreground">{d.status === "done" ? new Date(d.created_at).toLocaleDateString("fr-FR") : d.status === "running" ? "en cours" : "erreur"}</span>
            </button>
          ))}
        </section>
      )}
    </div>
  );
}
