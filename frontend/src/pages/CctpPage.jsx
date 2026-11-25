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

const UNITES = ["m2", "ml", "m3", "un", "vg"];
const EMPTY_PROJET = {
  nom: "", adresse: "", maitre_ouvrage: "", maitre_oeuvre: "", nature: "neuf", description: "", indice: "A", style: "economiste",
  tce: true, par_lots: false, delai: "", intervenants: { architecte: "", bet_structure: "", bet_fluides: "", bet_thermique: "", coordonnateur_sps: "", controleur_technique: "" },
  consultation: { date_limite: "", remise: "", visite: "", validite_jours: 90, variantes: true },
};
const INTERVENANTS = [["architecte", "Arquiteto / coordenador de projeto"], ["bet_structure", "Projeto de estabilidade"],
  ["bet_fluides", "Projetos de redes e instalações"], ["bet_thermique", "Projeto de comportamento térmico"],
  ["coordonnateur_sps", "Coordenador de segurança em obra"], ["controleur_technique", "Fiscalização"]];
const TYPES_PIECE = [["", "Tipo automático"], ["sejour", "Sala"], ["cuisine", "Cozinha"], ["chambre", "Quarto"], ["bureau", "Escritório"],
  ["sdb", "Casa de banho"], ["wc", "Instalação sanitária de serviço"], ["entree", "Hall de entrada"], ["circulation", "Corredor"],
  ["buanderie", "Lavandaria / despensa"], ["garage", "Garagem"], ["exterieur", "Exterior"], ["autre", "Outra"]];
const vazio = (code, extra = {}) => ({ code, numero: null, titre: "", inclure: [], ouvrages: [], lignes: [], notes: "", ...extra });
// Modelo « moradia unifamiliar » : capítulos de uma empreitada geral corrente em Portugal
const PRESET_MORADIA = {
  demolition: vazio("demolition", { ouvrages: ["estaleiro"] }),
  vrd: vazio("vrd"),
  gros_oeuvre: vazio("gros_oeuvre"),
  charpente_couverture: vazio("charpente_couverture"),
  menuiseries_ext: vazio("menuiseries_ext"),
  platrerie: vazio("platrerie", { titre: "Acabamentos interiores", inclure: ["menuiseries_int", "peinture", "sols_durs", "sols_souples"] }),
  plomberie: vazio("plomberie", { ouvrages: ["distribution", "evacuations", "ecs"] }),
  cvc: vazio("cvc", { ouvrages: ["pac_air_eau", "plancher_chauffant", "vmc"] }),
  electricite: vazio("electricite", { ouvrages: ["chantier_elec", "branchement", "terre"] }),
};
const DIVISOES_MORADIA = [
  ["Hall de entrada", "R/C"], ["Sala", "R/C"], ["Cozinha", "R/C"], ["Instalação sanitária de serviço", "R/C"], ["Lavandaria", "R/C"],
  ["Garagem", "R/C"], ["Quarto 1", "1.º piso"], ["Quarto 2", "1.º piso"], ["Suite", "1.º piso"], ["Casa de banho da suite", "1.º piso"],
  ["Casa de banho comum", "1.º piso"], ["Corredor", "1.º piso"],
].map(([nom, niveau]) => ({ nom, type: "", surface: null, niveau, extras: [] }));
const num = (n) => (n ? String(n).padStart(2, "0") : "—");

async function download(url, fallback) {
  try {
    const resp = await api.get(url, { responseType: "blob" });
    const href = URL.createObjectURL(resp.data);
    const a = document.createElement("a");
    a.href = href; a.download = filenameFromResponse(resp, fallback); a.click();
    URL.revokeObjectURL(href);
  } catch { toast.error("Não foi possível descarregar"); }
}

function LotCard({ lot, sel, onChange, catalogue, absorbe }) {
  const [open, setOpen] = useState(false);
  const active = !!sel;
  const toggle = (v) => onChange(v ? vazio(lot.code) : null);
  if (absorbe) {
    return (
      <div className="surface p-4 rounded-xl opacity-60 text-sm" data-testid={`cctp-lot-${lot.code}`}>
        <span className="text-xs text-muted-foreground">Capítulo</span>
        <p className="font-semibold leading-tight">{lot.titre}</p>
        <p className="text-xs mt-1">Agrupado em « {absorbe} »</p>
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
          <span className="text-xs text-muted-foreground">Capítulo {sel?.numero ? num(sel.numero) : ""}</span>
          <p className="font-semibold leading-tight">{sel?.titre || lot.titre}</p>
          {inclus.length > 0 && <p className="text-xs text-primary">+ {inclus.map((l) => l.titre.split(" – ")[0]).join(", ")}</p>}
        </button>
        {active && (open ? <ChevronDown size={18} /> : <ChevronRight size={18} />)}
      </div>
      {active && open && (
        <div className="mt-4 space-y-4">
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">N.º</span>
            <Input type="number" min={1} max={99} className="w-20 h-8" placeholder="auto" value={sel.numero ?? ""}
              onChange={(e) => upd({ numero: Number(e.target.value) || null })} />
            <Input className="h-8 flex-1" placeholder={`Título (por defeito : ${lot.titre})`} value={sel.titre || ""}
              onChange={(e) => upd({ titre: e.target.value })} />
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Agrupar neste capítulo</p>
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
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Artigos tipo (vazio = todos)</p>
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
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Trabalhos e quantidades do projeto</p>
            {sel.lignes.map((l, i) => (
              <div key={i} className="grid grid-cols-12 gap-2 mb-2">
                <Input className="col-span-12 sm:col-span-5 h-9" placeholder="Designação (ex. Divisória 72/48 em gesso cartonado)" value={l.designation}
                  onChange={(e) => setLigne(i, { designation: e.target.value })} />
                <select className="col-span-3 sm:col-span-1 h-9 rounded-md border bg-background px-1 text-sm" value={l.unite}
                  onChange={(e) => setLigne(i, { unite: e.target.value })}>
                  {UNITES.map((u) => <option key={u}>{u}</option>)}
                </select>
                <Input className="col-span-3 sm:col-span-2 h-9" type="number" min={0} step="0.01" placeholder="Quant." value={l.quantite ?? ""}
                  onChange={(e) => setLigne(i, { quantite: e.target.value === "" ? null : Number(e.target.value) })} />
                <Input className="col-span-5 sm:col-span-3 h-9" placeholder="Localização" value={l.localisation}
                  onChange={(e) => setLigne(i, { localisation: e.target.value })} />
                <Button variant="ghost" size="icon" className="col-span-1 h-9" onClick={() => upd({ lignes: sel.lignes.filter((_, j) => j !== i) })}>
                  <Trash2 size={16} />
                </Button>
              </div>
            ))}
            <Button variant="outline" size="sm" onClick={() => upd({ lignes: [...sel.lignes, { designation: "", unite: "m2", quantite: null, localisation: "" }] })}>
              <Plus size={15} className="me-1" /> Adicionar trabalho
            </Button>
          </div>
          <Textarea rows={2} placeholder="Instruções para este capítulo (materiais impostos, desempenhos, obra habitada…)" value={sel.notes}
            onChange={(e) => upd({ notes: e.target.value })} />
          <p className="text-xs text-muted-foreground">Referências : {lot.refs.map((r) => r.split(" — ")[0]).join(" · ")}</p>
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
    api.get("/pro/cctp/catalogue").then((r) => setCatalogue(r.data.lots || [])).catch(() => toast.error("Catálogo do caderno de encargos indisponível"));
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
    setSel(PRESET_MORADIA);
    setProjet((p) => ({ ...p, tce: true, par_lots: false }));
    if (!pieces.length) setPieces(DIVISOES_MORADIA);
    toast.success("Modelo moradia unifamiliar aplicado : ajuste os capítulos e as divisões");
  };

  const poll = (id) => {
    api.get(`/pro/cctp/dossiers/${id}`).then((r) => {
      setDossier(r.data);
      if (r.data.status === "running") timer.current = setTimeout(() => poll(id), 2500);
      else {
        setBusy(false); loadHistory();
        if (r.data.status === "done") toast.success("Caderno de encargos redigido");
        else toast.error(r.data.error || "Não foi possível redigir");
      }
    }).catch(() => { setBusy(false); toast.error("Não foi possível acompanhar a redação"); });
  };

  const generer = async () => {
    if (!projet.nom.trim()) return toast.error("Indique o nome da obra");
    if (!nbLots && !docId) return toast.error("Escolha pelo menos um capítulo ou um orçamento");
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
      toast.error(e?.response?.data?.detail || "Não foi possível redigir");
    }
  };

  const fichiers = dossier?.fichiers || [];
  return (
    <div className="max-w-6xl mx-auto px-5 py-8 space-y-6" data-testid="cctp-page">
      <div>
        <p className="overline text-primary">Peças escritas · Processo de concurso</p>
        <h1 className="font-display text-3xl sm:text-4xl font-bold flex items-center gap-3"><ScrollText /> Caderno de Encargos</h1>
        <p className="text-sm text-muted-foreground mt-2 max-w-3xl">
          O ConstruPilot redige o caderno de encargos por capítulos — capa com o seu logótipo, condições técnicas gerais e
          especiais, condições de execução segundo as normas portuguesas (NP EN, LNEC, RGEU, RTIEBT, ITED, DR 23/95), artigos
          com localização — e o mapa de quantidades de trabalho com a mesma numeração, prontos para o concurso.
        </p>
      </div>

      <section className="surface p-5 rounded-2xl space-y-3">
        <h2 className="font-semibold">1. Obra</h2>
        <div className="grid sm:grid-cols-2 gap-3">
          <Input placeholder="Nome da obra *" value={projet.nom} onChange={setP("nom")} data-testid="cctp-nom" />
          <Input placeholder="Morada da obra" value={projet.adresse} onChange={setP("adresse")} />
          <Input placeholder="Dono de obra" value={projet.maitre_ouvrage} onChange={setP("maitre_ouvrage")} />
          <Input placeholder="Autor do projeto" value={projet.maitre_oeuvre} onChange={setP("maitre_oeuvre")} />
        </div>
        <div className="flex flex-wrap items-center gap-4 text-sm">
          {[["neuf", "Construção nova"], ["renovation", "Reabilitação / remodelação"]].map(([v, l]) => (
            <label key={v} className="flex items-center gap-2 cursor-pointer">
              <input type="radio" name="nature" checked={projet.nature === v} onChange={() => setProjet({ ...projet, nature: v })} /> {l}
            </label>
          ))}
          <span className="flex items-center gap-2">Revisão <Input className="w-16 h-8" value={projet.indice} onChange={setP("indice")} /></span>
        </div>
        <Textarea rows={3} placeholder="Descrição da obra (tipologia, área, pisos, condicionantes, desempenhos pretendidos…) — ajuda a IA a adaptar os artigos"
          value={projet.description} onChange={setP("description")} />
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <span className="font-medium">Organização :</span>
          {[[false, "Empreitada geral (um só caderno com todos os capítulos)"], [true, "Empreitada por lotes (um caderno por capítulo)"]].map(([v, l]) => (
            <label key={String(v)} className="flex items-center gap-2 cursor-pointer">
              <input type="radio" name="par_lots" checked={projet.par_lots === v} onChange={() => setProjet({ ...projet, par_lots: v })} /> {l}
            </label>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <span className="font-medium">Estilo :</span>
          {[["economiste", "Medidor-orçamentista (artigos numerados)"], ["architecte", "Arquiteto (generalidades + descrição dos trabalhos)"]].map(([v, l]) => (
            <label key={v} className="flex items-center gap-2 cursor-pointer">
              <input type="radio" name="style" checked={projet.style === v} onChange={() => setProjet({ ...projet, style: v })} /> {l}
            </label>
          ))}
        </div>
        <details className="text-sm">
          <summary className="cursor-pointer font-medium">Intervenientes (capa e programa de concurso)</summary>
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
          <h2 className="font-semibold">Programa por divisão (opcional)</h2>
          <Button variant="outline" size="sm" className="ms-auto" onClick={appliquerModele} data-testid="cctp-modele-maison">
            <Sparkles size={15} className="me-1" /> Modelo moradia unifamiliar
          </Button>
        </div>
        <p className="text-sm text-muted-foreground">
          Os capítulos de Eletricidade e de Águas e esgotos passam a listar o equipamento de cada divisão (ITED 4 e RTIEBT ; o número de
          tomadas é uma base proposta, as RTIEBT não fixam mínimos por divisão) e o mapa de quantidades fica medido automaticamente.
        </p>
        {pieces.map((p, i) => (
          <div key={i} className="grid grid-cols-12 gap-2">
            <Input className="col-span-12 sm:col-span-4 h-9" placeholder="Divisão (ex. Quarto 1)" value={p.nom} onChange={(e) => setPiece(i, { nom: e.target.value })} />
            <select className="col-span-4 sm:col-span-2 h-9 rounded-md border bg-background px-1 text-sm" value={p.type} onChange={(e) => setPiece(i, { type: e.target.value })}>
              {TYPES_PIECE.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            <Input className="col-span-3 sm:col-span-1 h-9" type="number" min={0} placeholder="m²" value={p.surface ?? ""}
              onChange={(e) => setPiece(i, { surface: e.target.value === "" ? null : Number(e.target.value) })} />
            <Input className="col-span-4 sm:col-span-1 h-9" placeholder="Piso" value={p.niveau} onChange={(e) => setPiece(i, { niveau: e.target.value })} />
            <Input className="col-span-11 sm:col-span-3 h-9" placeholder="Equipamentos adicionais (separados por ;)" value={(p.extras || []).join("; ")}
              onChange={(e) => setPiece(i, { extras: e.target.value.split(";").map((x) => x.trim()).filter(Boolean) })} />
            <Button variant="ghost" size="icon" className="col-span-1 h-9" onClick={() => setPieces(pieces.filter((_, j) => j !== i))}><Trash2 size={16} /></Button>
          </div>
        ))}
        <Button variant="outline" size="sm" onClick={() => setPieces([...pieces, { nom: "", type: "", surface: null, niveau: "", extras: [] }])}>
          <Plus size={15} className="me-1" /> Adicionar divisão
        </Button>
      </section>

      <section className="surface p-5 rounded-2xl space-y-3">
        <h2 className="font-semibold">2. Partir de um orçamento (opcional)</h2>
        <p className="text-sm text-muted-foreground">As linhas do orçamento são ligadas aos capítulos e aos artigos tipo, com as quantidades.</p>
        <select className="h-10 w-full sm:w-2/3 rounded-md border bg-background px-3 text-sm" value={docId} onChange={(e) => setDocId(e.target.value)}
          data-testid="cctp-devis">
          <option value="">— Nenhum orçamento —</option>
          {devis.map((d) => <option key={d.doc_id} value={d.doc_id}>{[d.number, d.title].filter(Boolean).join(" · ")}</option>)}
        </select>
      </section>

      <section className="space-y-3">
        <h2 className="font-semibold">3. Capítulos a redigir {nbLots > 0 && <span className="text-primary">({nbLots})</span>}</h2>
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
          4. Peças do concurso : capa e índice do processo, programa de concurso, cláusulas gerais do caderno de encargos
        </label>
        {projet.tce && (
          <div className="grid sm:grid-cols-2 gap-3">
            <Input placeholder="Data limite de entrega das propostas" value={projet.consultation.date_limite}
              onChange={(e) => setProjet({ ...projet, consultation: { ...projet.consultation, date_limite: e.target.value } })} />
            <Input placeholder="Prazo de execução (ex. 10 meses)" value={projet.delai} onChange={setP("delai")} />
            <Textarea rows={4} className="sm:col-span-2" placeholder={"Peças desenhadas, uma por linha\nPlanta de implantação\nPlanta do R/C 1/50\nProjeto de instalações elétricas…"}
              value={plans} onChange={(e) => setPlans(e.target.value)} />
          </div>
        )}
      </section>

      <section className="surface p-5 rounded-2xl flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-3 text-sm">
          <Switch checked={ia} onCheckedChange={setIa} />
          <span><Sparkles size={14} className="inline me-1 text-primary" />Redação adaptada à obra pela IA</span>
        </label>
        <span className="text-xs text-muted-foreground flex items-center gap-1">
          <ShieldCheck size={14} /> Normas verificadas em lista branca · quantidades nunca inventadas
        </span>
        <Button className="ms-auto" onClick={generer} disabled={busy} data-testid="cctp-generer">
          {busy ? <Loader2 size={16} className="animate-spin me-2" /> : <ScrollText size={16} className="me-2" />}
          {busy ? "A redigir…" : "Redigir o caderno de encargos"}
        </Button>
      </section>

      {dossier && dossier.status === "done" && (
        <section className="surface p-5 rounded-2xl space-y-4" data-testid="cctp-resultat">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="font-semibold">Processo pronto — {dossier.projet?.nom}</h2>
            <Button size="sm" className="ms-auto" onClick={() => download(`/pro/cctp/dossiers/${dossier.dossier_id}/zip`, "Concurso.zip")}>
              <Archive size={15} className="me-1" /> Descarregar o processo (.zip)
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
            <h3 className="text-sm font-semibold">Pontos a verificar pelo redator</h3>
            {(dossier.lots || []).map((l) => (
              <div key={l.code} className="text-sm">
                <p className="font-medium">Capítulo {num(l.numero)} — {l.titre}
                  <span className="text-muted-foreground"> · {l.articles} artigos · {l.lignes} linhas no mapa · {l.mode === "ia" ? "redação IA" : "artigos tipo"}</span></p>
                <ul className="list-disc ms-5 text-muted-foreground">
                  {(l.points.length ? l.points : ["Nenhum ponto assinalado."]).map((p, i) => <li key={i}>{p}</li>)}
                </ul>
              </div>
            ))}
          </div>
        </section>
      )}

      {historique.length > 0 && (
        <section className="space-y-2">
          <h2 className="font-semibold">Processos recentes</h2>
          {historique.map((d) => (
            <button key={d.dossier_id} type="button" className="w-full surface p-3 rounded-lg flex items-center gap-3 text-sm text-left"
              onClick={() => d.status === "done" ? setDossier(d) : poll(d.dossier_id)}>
              <ScrollText size={16} className="text-primary" />
              <span className="flex-1">{d.projet?.nom} · {(d.lots || []).length} capítulo(s)</span>
              <span className="text-muted-foreground">{d.status === "done" ? new Date(d.created_at).toLocaleDateString("pt-PT") : d.status === "running" ? "em curso" : "erro"}</span>
            </button>
          ))}
        </section>
      )}
    </div>
  );
}
