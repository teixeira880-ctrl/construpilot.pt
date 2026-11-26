import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  DraftingCompass, PenTool, Camera, Sparkles, Loader2, FolderOpen, Trash2, ArrowLeft, FileText, Archive, Box, Layers3, ScrollText,
  AlertTriangle, CheckCircle2, Plus,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { filenameFromResponse } from "@/lib/downloadName";
import { useI18n } from "@/context/I18nContext";
import CroquisCanvas from "@/components/atelier/CroquisCanvas";
import AssistenteSimples from "@/components/atelier/AssistenteSimples";

const Studio = lazy(() => import("@/components/licenciamento/EstudioProjeto"));      // three.js : carregado ao abrir um projeto

const COPY = {
  fr: {
    titre: "Atelier Architecte", sous: "Esquissez à la main, depuis une photo de croquis ou par une simple phrase : ConstruPilot en fait une maquette "
      + "(plans cotés, façades, coupes, 3D, métré, DXF, IFC) puis le DCE complet — CCTP par lot et DPGF — en français.",
    simples: "Mode simple", main: "Dessin à main levée", photo: "Photo d'un croquis", prompt: "Décrire le projet",
    promptAide: "Décrivez la maison comme à un confrère : typologie, surface, niveaux, garage, toiture…",
    exemples: ["Maison T4 plain-pied 110 m² avec garage et cuisine ouverte", "Maison R+1 4 chambres dont une suite parentale, bureau, buanderie, double garage, toit plat",
      "Petite maison T3 de 80 m², toiture 4 pans"],
    generer: "Générer l'esquisse", photoAide: "Photographiez le croquis bien à plat, en entier, avec les cotes lisibles. Les murs, ouvertures, noms de pièces et cotes sont relus puis redressés.",
    choisir: "Choisir ou prendre une photo", lire: "Lire le croquis",
    apercu: "Esquisse", niveau: "Niveau", pieces: "Pièces", surface: "Surface utile", sb: "Surface construite", avis: "À vérifier", pedidos: "Demandes du prompt", verif: "Vérification avant validation", actualiser: "Actualiser", nOk: "conformes", nAviso: "à revoir", nFalha: "non conformes", voirTout: "Tout voir", masquer: "Masquer les points conformes", gerado: "généré", estudio: "à compléter dans le Studio", continuar: "Continuer dans",
    creer: "Créer le projet et ouvrir le Studio", nomProjet: "Nom du projet", adresse: "Adresse (facultatif)", moa: "Maître d'ouvrage (facultatif)",
    projets: "Mes projets d'architecture", aucun: "Aucun projet pour l'instant : commencez par une esquisse ci-dessus.", ouvrir: "Ouvrir",
    supprimer: "Supprimer", confirmerSup: "Supprimer définitivement ce projet ?", retour: "Mes projets",
    dce: "Générer le DCE (CCTP + DPGF)", dceTitre: "DCE depuis la maquette", dceAide: "Les quantités viennent du métré de la maquette (surfaces nettes, baies déduites). "
      + "Les ouvrages que la maquette ne mesure pas sont cités sans quantité.", lancer: "Rédiger le DCE", ia: "Rédaction assistée par IA (articles adaptés au projet)",
    moe: "Maître d'œuvre (facultatif)", enCours: "Rédaction en cours…", fini: "DCE rédigé", zip: "Télécharger le DCE (.zip)", voirCctp: "Ouvrir dans le Rédacteur CCTP",
    lots: "lots", lignes: "lignes", outils: "Avec la maquette", bimStudio: "ConstruPilot BIM Studio (IFC → métré et budget)", bimViewer: "Plans BIM / Autodesk",
    cctp: "Rédacteur CCTP · DCE", enregistrez: "Enregistrez la maquette avant de rédiger le DCE.", erreur: "Action impossible.",
  },
  pt: {
    titre: "Atelier do Arquiteto", sous: "Esboce à mão, a partir de uma fotografia de um esboço ou com uma simples frase: o ConstruPilot faz o modelo "
      + "(plantas cotadas, alçados, cortes, 3D, medições, DXF, IFC) e depois o DCE completo — CCTP por lote e DPGF — em francês.",
    simples: "Modo simples", main: "Desenho à mão levantada", photo: "Fotografia de um esboço", prompt: "Descrever o projeto",
    promptAide: "Descreva a moradia como a um colega: tipologia, área, pisos, garagem, cobertura…",
    exemples: ["Moradia T3 térrea 120 m² com garagem e cozinha aberta", "Moradia V4 de dois pisos com suite, escritório, lavandaria e garagem dupla, cobertura plana",
      "Pequena moradia T2 de 80 m², cobertura de quatro águas"],
    generer: "Gerar o esboço", photoAide: "Fotografe o esboço bem plano, inteiro, com as cotas legíveis. Paredes, vãos, nomes das divisões e cotas são lidos e endireitados.",
    choisir: "Escolher ou tirar uma fotografia", lire: "Ler o esboço",
    apercu: "Esboço", niveau: "Piso", pieces: "Divisões", surface: "Área útil", sb: "Área de construção", avis: "A verificar", pedidos: "Pedidos do prompt", verif: "Verificação antes de validar", actualiser: "Atualizar", nOk: "conformes", nAviso: "a rever", nFalha: "não conformes", voirTout: "Ver tudo", masquer: "Esconder os pontos conformes", gerado: "gerado", estudio: "a completar no Estúdio", continuar: "Continuar em",
    creer: "Criar o projeto e abrir o Estúdio", nomProjet: "Nome do projeto", adresse: "Morada (opcional)", moa: "Dono de obra (opcional)",
    projets: "Os meus projetos de arquitetura", aucun: "Ainda sem projetos: comece por um esboço acima.", ouvrir: "Abrir",
    supprimer: "Eliminar", confirmerSup: "Eliminar definitivamente este projeto?", retour: "Os meus projetos",
    dce: "Gerar o DCE (CCTP + DPGF)", dceTitre: "DCE a partir do modelo", dceAide: "As quantidades vêm das medições do modelo (áreas líquidas, vãos deduzidos). "
      + "Os trabalhos que o modelo não mede são citados sem quantidade. Documentos em francês.", lancer: "Redigir o DCE", ia: "Redação assistida por IA (artigos adaptados ao projeto)",
    moe: "Projetista / maître d'œuvre (opcional)", enCours: "Redação em curso…", fini: "DCE redigido", zip: "Descarregar o DCE (.zip)", voirCctp: "Abrir no Redator CCTP",
    lots: "lotes", lignes: "linhas", outils: "Com o modelo", bimStudio: "ConstruPilot BIM Studio (IFC → medições e orçamento)", bimViewer: "Plantas BIM / Autodesk",
    cctp: "Redator CCTP · DCE", enregistrez: "Guarde o modelo antes de redigir o DCE.", erreur: "Ação impossível.",
  },
  en: {
    titre: "Architect Studio", sous: "Sketch by hand, from a photo of a sketch or with a single sentence: ConstruPilot turns it into a model "
      + "(dimensioned plans, elevations, sections, 3D, take-off, DXF, IFC) and then the full tender package — CCTP per lot and DPGF — in French.",
    simples: "Simple mode", main: "Freehand drawing", photo: "Photo of a sketch", prompt: "Describe the project",
    promptAide: "Describe the house as you would to a colleague: type, area, storeys, garage, roof…",
    exemples: ["Single-storey 3-bedroom house, 110 m², garage, open kitchen", "Two-storey house, 4 bedrooms with master suite, office, laundry, double garage, flat roof",
      "Small 2-bedroom house of 80 m², hip roof"],
    generer: "Generate the sketch", photoAide: "Photograph the sketch flat, in full, with readable dimensions. Walls, openings, room names and dimensions are read then straightened.",
    choisir: "Choose or take a photo", lire: "Read the sketch",
    apercu: "Sketch", niveau: "Level", pieces: "Rooms", surface: "Usable area", sb: "Gross floor area", avis: "To check", pedidos: "Prompt requests", verif: "Check before validation", actualiser: "Refresh", nOk: "compliant", nAviso: "to review", nFalha: "non-compliant", voirTout: "Show all", masquer: "Hide compliant items", gerado: "generated", estudio: "to complete in the Studio", continuar: "Continue in",
    creer: "Create the project and open the Studio", nomProjet: "Project name", adresse: "Address (optional)", moa: "Client (optional)",
    projets: "My architecture projects", aucun: "No project yet: start with a sketch above.", ouvrir: "Open",
    supprimer: "Delete", confirmerSup: "Delete this project permanently?", retour: "My projects",
    dce: "Generate the tender package (CCTP + DPGF)", dceTitre: "Tender package from the model", dceAide: "Quantities come from the model take-off (net areas, openings deducted). "
      + "Items the model does not measure are listed without quantity. Documents in French.", lancer: "Write the package", ia: "AI-assisted writing (articles adapted to the project)",
    moe: "Project architect (optional)", enCours: "Writing…", fini: "Package written", zip: "Download the package (.zip)", voirCctp: "Open in the CCTP writer",
    lots: "lots", lignes: "lines", outils: "With the model", bimStudio: "BIM Studio (IFC → take-off and budget)", bimViewer: "BIM / Autodesk plans",
    cctp: "CCTP · tender writer", enregistrez: "Save the model before writing the package.", erreur: "Action failed.",
  },
};

async function telecharger(url, nom) {
  try {
    const r = await api.get(url, { responseType: "blob", timeout: 180000 });
    const href = URL.createObjectURL(r.data);
    const a = document.createElement("a");
    a.href = href; a.download = filenameFromResponse(r, nom); a.click();
    setTimeout(() => URL.revokeObjectURL(href), 4000);
  } catch { toast.error("Téléchargement impossible"); }
}

function PlanSvg({ modelo, piso }) {
  const [url, setUrl] = useState(null);
  useEffect(() => {
    let vivo = true, u = null;
    api.post("/atelier-archi/desenho.svg", { modelo, tipo: "planta", piso }, { responseType: "blob", timeout: 60000 })
      .then((r) => { if (vivo) { u = URL.createObjectURL(r.data); setUrl(u); } })
      .catch(() => { if (vivo) setUrl(null); });
    return () => { vivo = false; if (u) URL.revokeObjectURL(u); };
  }, [modelo, piso]);
  if (!url) return <div className="h-72 grid place-items-center text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" /></div>;
  return <img src={url} alt="" className="w-full rounded-lg border border-border bg-white" data-testid="atelier-plan-svg" />;
}

// Tudo o que o prompt pede fica visível: o que é gerado aqui, o que se completa no Estúdio
// e o que continua noutra app — no mesmo processo de obra (fluxo entre apps).
function PedidosPrompt({ pedidos, c }) {
  const [sp] = useSearchParams();
  const ch = sp.get("chantier");
  return (
    <div className="rounded-lg border border-border p-2.5 space-y-1.5" data-testid="atelier-pedidos">
      <p className="font-medium flex items-center gap-1"><ScrollText className="h-4 w-4" />{c.pedidos}</p>
      {pedidos.map((p, i) => (
        <div key={i} className="flex items-start justify-between gap-2 text-xs">
          <span className="flex items-start gap-1">
            {p.estado === "gerado" ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 shrink-0 mt-px" /> : <span className="h-1.5 w-1.5 rounded-full bg-primary shrink-0 mt-1.5" />}
            <span>{p.titulo}{p.estado === "gerado" ? ` — ${c.gerado}` : p.estado === "estudio" ? ` — ${c.estudio}` : ""}</span>
          </span>
          {p.estado === "continuar" && (
            <Link to={ch ? `${p.rota}?chantier=${encodeURIComponent(ch)}` : p.rota} className="shrink-0 text-primary font-semibold hover:underline"
              data-testid={`atelier-pedido-${i}`}>{c.continuar} {p.app}</Link>
          )}
        </div>
      ))}
    </div>
  );
}

function Apercu({ data, c, onCreer, enCours }) {
  const [piso, setPiso] = useState(0);
  const [titre, setTitre] = useState("");
  const [adresse, setAdresse] = useState("");
  const [moa, setMoa] = useState("");
  const r = data.resume || {};
  const niveaux = data.modelo?.pisos || [];
  return (
    <section className="surface rounded-2xl p-4 sm:p-5 space-y-4" data-testid="atelier-apercu">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold">{c.apercu}</h2>
        {niveaux.length > 1 && niveaux.map((n, i) => (
          <Button key={n.id} size="sm" variant={piso === i ? "secondary" : "ghost"} onClick={() => setPiso(i)}>{n.nome}</Button>
        ))}
        <span className="ml-auto text-sm text-muted-foreground">
          {c.surface} {String(r.surface_utile_m2 ?? "—").replace(".", ",")} m² · {c.sb} {String(r.surface_construite_m2 ?? "—").replace(".", ",")} m²
        </span>
      </div>
      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <PlanSvg modelo={data.modelo} piso={piso} />
        <div className="space-y-3 text-sm">
          <div>
            <p className="font-medium mb-1">{c.pieces}</p>
            <ul className="space-y-0.5 max-h-56 overflow-auto">
              {(r.pieces || []).filter((p) => p.niveau === niveaux[piso]?.id).map((p, i) => (
                <li key={i} className="flex justify-between gap-2"><span>{p.nom}</span><span className="text-muted-foreground">{String(p.surface_m2).replace(".", ",")} m²</span></li>
              ))}
            </ul>
          </div>
          {!!(data.avisos || []).length && (
            <div className="rounded-lg bg-amber-50 border border-amber-200 p-2.5 space-y-1">
              <p className="font-medium text-amber-900 flex items-center gap-1"><AlertTriangle className="h-4 w-4" />{c.avis}</p>
              {data.avisos.map((a, i) => <p key={i} className="text-xs text-amber-900">• {a}</p>)}
            </div>
          )}
          {!!(data.pedidos || []).length && <PedidosPrompt pedidos={data.pedidos} c={c} />}
          <Verificacao dados={data.verificacao} c={c} />
        </div>
      </div>
      <div className="grid gap-2 sm:grid-cols-3">
        <Input placeholder={c.nomProjet} value={titre} onChange={(e) => setTitre(e.target.value)} data-testid="atelier-titre" />
        <Input placeholder={c.adresse} value={adresse} onChange={(e) => setAdresse(e.target.value)} />
        <Input placeholder={c.moa} value={moa} onChange={(e) => setMoa(e.target.value)} />
      </div>
      <div className="flex justify-end">
        <Button disabled={!titre.trim() || enCours} onClick={() => onCreer({ titre: titre.trim(), adresse, maitre_ouvrage: moa })} data-testid="atelier-creer">
          {enCours ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Plus className="h-4 w-4 mr-1" />}{c.creer}
        </Button>
      </div>
    </section>
  );
}

// Verificação antes de validar: regras com fonte (RGEU em Portugal, décret 2002-120 / RSD em França) e programa
// pedido vs modelo. Indicativa: a nota do motor lembra que não substitui o técnico habilitado.
function Verificacao({ dados, c, onAtualizar, carregando }) {
  const [tudo, setTudo] = useState(false);
  if (!dados) return null;
  const r = dados.resumo || {};
  const cor = { ok: "text-emerald-700", aviso: "text-amber-700", falha: "text-red-700" };
  const lista = (dados.resultados || []).filter((x) => tudo || x.estado !== "ok");
  return (
    <div className="rounded-lg border border-border p-2.5 space-y-1.5" data-testid="atelier-verificacao">
      <div className="flex flex-wrap items-center gap-2">
        <p className="font-medium flex items-center gap-1">
          {dados.conforme ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : <AlertTriangle className="h-4 w-4 text-red-600" />}{c.verif}
        </p>
        <span className="text-xs text-muted-foreground">
          <b className={cor.ok}>{r.ok || 0}</b> {c.nOk} · <b className={cor.aviso}>{r.aviso || 0}</b> {c.nAviso} · <b className={cor.falha}>{r.falha || 0}</b> {c.nFalha}
        </span>
        <span className="ml-auto flex gap-1">
          <Button size="sm" variant="ghost" onClick={() => setTudo(!tudo)}>{tudo ? c.masquer : c.voirTout}</Button>
          {onAtualizar && <Button size="sm" variant="outline" onClick={onAtualizar} disabled={carregando}>
            {carregando ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : c.actualiser}</Button>}
        </span>
      </div>
      <ul className="space-y-0.5 max-h-64 overflow-auto">
        {lista.map((x, i) => (
          <li key={i} className="text-xs flex gap-2">
            <span className={`shrink-0 font-semibold ${cor[x.estado] || ""}`}>{x.estado === "ok" ? "✓" : x.estado === "aviso" ? "!" : "✗"}</span>
            <span><b>{x.regra}</b> — {x.msg} <span className="text-muted-foreground">({x.fonte})</span></span>
          </li>
        ))}
      </ul>
      {dados.nota && <p className="text-[11px] text-muted-foreground">{dados.nota}</p>}
    </div>
  );
}

function VerificacaoProjeto({ pid, c }) {
  const [dados, setDados] = useState(null);
  const [carregando, setCarregando] = useState(false);
  const carregar = useCallback(async () => {
    setCarregando(true);
    try { const { data } = await api.get(`/atelier-archi/projets/${pid}/verificacao`); setDados(data); } catch { /* painel opcional */ }
    setCarregando(false);
  }, [pid]);
  useEffect(() => { carregar(); }, [carregar]);
  return <section className="surface rounded-2xl p-4"><Verificacao dados={dados} c={c} onAtualizar={carregar} carregando={carregando} /></section>;
}

function DcePanel({ pid, c, projet }) {
  const [apercu, setApercu] = useState(null);
  const [ia, setIa] = useState(true);
  const [moe, setMoe] = useState("");
  const [dossier, setDossier] = useState(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef(null);
  useEffect(() => () => clearTimeout(timer.current), []);
  useEffect(() => {
    api.get(`/atelier-archi/projets/${pid}/dce/apercu`).then((r) => setApercu(r.data)).catch(() => setApercu(null));
  }, [pid]);
  const suivre = useCallback((id) => {
    api.get(`/pro/cctp/dossiers/${id}`).then((r) => {
      setDossier(r.data);
      if (r.data.status === "running") timer.current = setTimeout(() => suivre(id), 2500);
      else { setBusy(false); if (r.data.status === "done") toast.success(c.fini); else toast.error(r.data.error || c.erreur); }
    }).catch(() => setBusy(false));
  }, [c]);
  useEffect(() => { if (projet?.dce_id) suivre(projet.dce_id); }, [projet?.dce_id, suivre]);
  const lancer = async () => {
    setBusy(true); setDossier(null);
    try {
      const { data } = await api.post(`/atelier-archi/projets/${pid}/dce`, { ia, maitre_oeuvre: moe });
      suivre(data.dossier_id);
    } catch (e) { setBusy(false); toast.error(e?.response?.data?.detail || c.erreur); }
  };
  return (
    <section className="surface rounded-2xl p-4 sm:p-5 space-y-3" data-testid="atelier-dce">
      <h2 className="text-lg font-semibold flex items-center gap-2"><ScrollText className="h-5 w-5 text-primary" />{c.dceTitre}</h2>
      <p className="text-sm text-muted-foreground">{c.dceAide}</p>
      {apercu && (
        <div className="flex flex-wrap gap-1.5">
          {apercu.resume.lots.map((l) => (
            <span key={l.code} className="text-xs rounded-full border border-border px-2.5 py-1 bg-card">{l.titre} · {l.lignes} {c.lignes}</span>
          ))}
        </div>
      )}
      <div className="grid gap-2 sm:grid-cols-[1fr_auto] items-center">
        <Input placeholder={c.moe} value={moe} onChange={(e) => setMoe(e.target.value)} />
        <label className="flex items-center gap-2 text-sm"><Switch checked={ia} onCheckedChange={setIa} />{c.ia}</label>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={lancer} disabled={busy} data-testid="atelier-dce-lancer">
          {busy ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <FileText className="h-4 w-4 mr-1" />}{busy ? c.enCours : c.lancer}
        </Button>
        {dossier?.status === "done" && (
          <>
            <span className="text-sm text-emerald-700 flex items-center gap-1"><CheckCircle2 className="h-4 w-4" />{c.fini} · {(dossier.lots || []).length} {c.lots}</span>
            <Button variant="outline" onClick={() => telecharger(`/pro/cctp/dossiers/${dossier.dossier_id}/zip`, "DCE.zip")} data-testid="atelier-dce-zip">
              <Archive className="h-4 w-4 mr-1" />{c.zip}</Button>
            <Button variant="ghost" asChild><Link to="/cctp">{c.voirCctp}</Link></Button>
          </>
        )}
      </div>
      {dossier?.status === "done" && (
        <ul className="text-xs text-muted-foreground grid sm:grid-cols-2 gap-x-4">
          {(dossier.fichiers || []).map((f) => (
            <li key={f.index}>
              <button type="button" className="hover:text-primary underline-offset-2 hover:underline text-left"
                onClick={() => telecharger(`/pro/cctp/dossiers/${dossier.dossier_id}/fichiers/${f.index}`, f.nom)}>{f.nom}</button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function AtelierArchitecte() {
  const { lang } = useI18n();
  const c = COPY[lang] || COPY.pt;
  const [params, setParams] = useSearchParams();
  const pid = params.get("projet");
  const [mode, setMode] = useState("simples");
  const [prompt, setPrompt] = useState("");
  const [photo, setPhoto] = useState(null);
  const [busy, setBusy] = useState(false);
  const [esquisse, setEsquisse] = useState(null);
  const [origine, setOrigine] = useState("croquis");
  const [projets, setProjets] = useState(null);
  const [projet, setProjet] = useState(null);

  const charger = useCallback(() => {
    api.get("/atelier-archi/projets").then((r) => setProjets(r.data.projets)).catch(() => setProjets([]));
  }, []);
  useEffect(() => { if (!pid) charger(); }, [pid, charger]);
  useEffect(() => {
    if (!pid) { setProjet(null); return; }
    api.get(`/atelier-archi/projets/${pid}`).then((r) => setProjet(r.data.projet)).catch(() => { toast.error(c.erreur); setParams({}); });
  }, [pid]); // eslint-disable-line react-hooks/exhaustive-deps

  const esquisser = async (url, body, orig) => {
    setBusy(true); setEsquisse(null);
    try {
      const { data } = await api.post(url, body, { timeout: 180000 });
      setEsquisse(data); setOrigine(orig);
      setTimeout(() => document.querySelector("[data-testid=atelier-apercu]")?.scrollIntoView({ behavior: "smooth" }), 80);
    } catch (e) { toast.error(e?.response?.data?.detail || c.erreur); }
    setBusy(false);
  };
  const lirePhoto = (f) => {
    if (!f) return;
    const r = new FileReader();
    r.onload = () => setPhoto(String(r.result));
    r.readAsDataURL(f);
  };
  const creer = async (meta) => {
    setBusy(true);
    try {
      const { data } = await api.post("/atelier-archi/projets", {
        ...meta, modelo: esquisse.modelo, origine: origine, programme: origine === "prompt" ? prompt : "",
      });
      setEsquisse(null);
      setParams({ projet: data.projet_id });
    } catch (e) { toast.error(e?.response?.data?.detail || c.erreur); }
    setBusy(false);
  };
  const supprimer = async (id) => {
    if (!window.confirm(c.confirmerSup)) return;
    try { await api.delete(`/atelier-archi/projets/${id}/definitif`); charger(); } catch { toast.error(c.erreur); }
  };

  const outils = useMemo(() => [
    { to: "/bim", icon: Layers3, label: c.bimStudio }, { to: "/plans-pro", icon: Box, label: c.bimViewer }, { to: "/cctp", icon: ScrollText, label: c.cctp },
  ], [c]);

  if (pid) {
    return (
      <div className="mx-auto max-w-[1500px] px-4 lg:px-8 py-5 space-y-4" data-testid="atelier-projet">
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => setParams({})}><ArrowLeft className="h-4 w-4 mr-1" />{c.retour}</Button>
          <h1 className="text-xl font-bold tracking-tight">{projet?.titre || "…"}</h1>
          <span className="ml-auto flex flex-wrap gap-1.5">
            {outils.map((o) => (
              <Button key={o.to} size="sm" variant="outline" asChild><Link to={o.to}><o.icon className="h-4 w-4 mr-1" />{o.label}</Link></Button>
            ))}
          </span>
        </div>
        <Suspense fallback={<div className="h-96 grid place-items-center"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>}>
          <Studio pid={pid} base={`/atelier-archi/projets/${pid}`} apiEstudio="/atelier-archi" semProcesso
            textoRepor={lang === "pt" ? "Voltar ao esboço inicial? As alterações feitas no Estúdio serão apagadas." : lang === "en"
              ? "Go back to the initial sketch? Changes made in the Studio will be lost." : "Revenir à l'esquisse de départ ? Les modifications faites dans le Studio seront effacées."} />
        </Suspense>
        <p className="text-xs text-muted-foreground">{c.enregistrez}</p>
        <VerificacaoProjeto pid={pid} c={c} />
        <DcePanel pid={pid} c={c} projet={projet} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl px-4 sm:px-6 py-6 space-y-5" data-testid="atelier-architecte">
      <header className="flex items-start gap-3">
        <div className="h-12 w-12 rounded-2xl bg-primary/10 grid place-items-center shrink-0"><DraftingCompass className="h-6 w-6 text-primary" /></div>
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">{c.titre}</h1>
          <p className="mt-1 text-sm sm:text-base text-muted-foreground max-w-3xl">{c.sous}</p>
        </div>
      </header>

      <div className="flex flex-wrap gap-2">
        {[["simples", DraftingCompass, c.simples], ["main", PenTool, c.main], ["photo", Camera, c.photo], ["prompt", Sparkles, c.prompt]].map(([k, Icon, t]) => (
          <Button key={k} variant={mode === k ? "default" : "outline"} onClick={() => setMode(k)} data-testid={`atelier-mode-${k}`}>
            <Icon className="h-4 w-4 mr-1" />{t}
          </Button>
        ))}
      </div>

      <section className="surface rounded-2xl p-4 sm:p-5">
        {mode === "main" && (
          <CroquisCanvas lang={lang} enCours={busy} onRedresser={(b) => esquisser("/atelier-archi/esquisse/croquis", b, "croquis")} />
        )}
        {mode === "photo" && (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">{c.photoAide}</p>
            <label className="inline-flex items-center gap-2 cursor-pointer rounded-lg border border-dashed border-border px-4 py-3 hover:border-primary/60">
              <Camera className="h-5 w-5 text-primary" /><span className="text-sm">{c.choisir}</span>
              <input type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => lirePhoto(e.target.files?.[0])} data-testid="atelier-photo" />
            </label>
            {photo && <img src={photo} alt="" className="max-h-80 rounded-lg border border-border" />}
            <div className="flex justify-end">
              <Button disabled={!photo || busy} onClick={() => esquisser("/atelier-archi/esquisse/photo", { image_b64: photo }, "photo")}>
                {busy ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Sparkles className="h-4 w-4 mr-1" />}{c.lire}
              </Button>
            </div>
          </div>
        )}
        {mode === "simples" && (
          <AssistenteSimples lang={lang} ocupado={busy} onGerar={(texto) => { setPrompt(texto); esquisser("/atelier-archi/esquisse/prompt", { prompt: texto }, "prompt"); }} />
        )}
        {mode === "prompt" && (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">{c.promptAide}</p>
            <Textarea rows={3} value={prompt} onChange={(e) => setPrompt(e.target.value)} data-testid="atelier-prompt" />
            <div className="flex flex-wrap gap-1.5">
              {c.exemples.map((x) => (
                <button key={x} type="button" className="text-xs rounded-full border border-border px-2.5 py-1 hover:border-primary/60" onClick={() => setPrompt(x)}>{x}</button>
              ))}
            </div>
            <div className="flex justify-end">
              <Button disabled={prompt.trim().length < 3 || busy} onClick={() => esquisser("/atelier-archi/esquisse/prompt", { prompt }, "prompt")} data-testid="atelier-generer">
                {busy ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Sparkles className="h-4 w-4 mr-1" />}{c.generer}
              </Button>
            </div>
          </div>
        )}
      </section>

      {esquisse && <Apercu data={esquisse} c={c} onCreer={creer} enCours={busy} />}

      <section className="space-y-2">
        <h2 className="text-lg font-semibold flex items-center gap-2"><FolderOpen className="h-5 w-5 text-primary" />{c.projets}</h2>
        {projets === null ? <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /> : !projets.length ? (
          <p className="text-sm text-muted-foreground">{c.aucun}</p>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {projets.map((p) => (
              <div key={p.projet_id} className="rounded-xl border border-border bg-card p-3 flex items-center gap-2" data-testid={`atelier-projet-${p.projet_id}`}>
                <div className="flex-1 min-w-0">
                  <p className="font-medium truncate">{p.titre}</p>
                  <p className="text-xs text-muted-foreground">{p.origine} · {new Date(p.updated_at).toLocaleDateString(lang === "pt" ? "pt-PT" : lang === "en" ? "en-GB" : "fr-FR")}</p>
                </div>
                <Button size="sm" onClick={() => setParams({ projet: p.projet_id })}>{c.ouvrir}</Button>
                <Button size="sm" variant="ghost" aria-label={c.supprimer} onClick={() => supprimer(p.projet_id)}><Trash2 className="h-4 w-4" /></Button>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
