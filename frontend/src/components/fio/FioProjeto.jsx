// Fio do projeto: do desenho ao dossier final, sem perder dados. Mostra as etapas (feitas, por fazer, a refazer
// porque o desenho mudou), junta imagens 3D / renders / fotos e abre o Assistente já com o projeto carregado.
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { AlertTriangle, CheckCircle2, Circle, FileDown, ImagePlus, Loader2, MessageSquare, Thermometer, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

const COPY = {
  pt: {
    titulo: "Seguimento do projeto", sub: "Tudo parte deste desenho: cada etapa fica ligada à geometria em que foi feita.",
    assistente: "Continuar no Assistente", dossier: "Dossier final (PDF)", imagem: "Juntar imagem 3D / render / foto",
    imagens: "Imagens do dossier", refazer: "O desenho mudou depois desta etapa: refazer.", erro: "Ação impossível.",
    juntada: "Imagem juntada ao dossier.", tipos: { bim: "BIM 3D", render: "Render real", foto: "Foto", planta: "Planta", outra: "Outra" },
    legenda: "Legenda (opcional)", vazio: "Ainda sem imagens: junte vistas 3D do BIM, renders reais ou fotos do terreno.",
    termica: "Estudo térmico", zonaI: "Zona de inverno", zonaV: "Zona de verão", indicacoes: "Indicações para cumprir", faltam: "Dados a fornecer",
  },
  fr: {
    titulo: "Suivi du projet", sub: "Tout part de ce dessin : chaque étape reste liée à la géométrie sur laquelle elle a été faite.",
    assistente: "Continuer dans l'Assistant", dossier: "Dossier final (PDF)", imagem: "Joindre une image 3D / un rendu / une photo",
    imagens: "Images du dossier", refazer: "Le dessin a changé après cette étape : à refaire.", erro: "Action impossible.",
    juntada: "Image jointe au dossier.", tipos: { bim: "BIM 3D", render: "Rendu réel", foto: "Photo", planta: "Plan", outra: "Autre" },
    legenda: "Légende (facultative)", vazio: "Pas encore d'images : joignez des vues 3D du BIM, des rendus réels ou des photos du terrain.",
    termica: "Étude thermique", zonaI: "", zonaV: "", indicacoes: "Indications pour être conforme", faltam: "Données à fournir",
  },
  en: {
    titulo: "Project thread", sub: "Everything starts from this drawing: each step stays linked to the geometry it was made on.",
    assistente: "Continue in the Assistant", dossier: "Final dossier (PDF)", imagem: "Add a 3D view / render / photo",
    imagens: "Dossier images", refazer: "The drawing changed after this step: redo it.", erro: "Action failed.",
    juntada: "Image added to the dossier.", tipos: { bim: "BIM 3D", render: "Real render", foto: "Photo", planta: "Plan", outra: "Other" },
    legenda: "Caption (optional)", vazio: "No images yet: add BIM 3D views, real renders or site photos.",
    termica: "Thermal study", zonaI: "Winter zone", zonaV: "Summer zone", indicacoes: "What to change to comply", faltam: "Data to provide",
  },
};

function Miniatura({ pid, im, onApagar }) {
  const [url, setUrl] = useState(null);
  useEffect(() => {
    let vivo = true, u = null;
    api.get(`/fio-projeto/${encodeURIComponent(pid)}/imagens/${im.imagem_id}`, { responseType: "blob" })
      .then((r) => { if (!vivo) return; u = URL.createObjectURL(r.data); setUrl(u); }).catch(() => {});
    return () => { vivo = false; if (u) URL.revokeObjectURL(u); };
  }, [pid, im.imagem_id]);
  return (
    <figure className="relative rounded-lg border border-border overflow-hidden bg-muted/30" data-testid="fio-imagem">
      {url ? <img src={url} alt={im.legenda || ""} className="h-28 w-full object-cover" /> : <div className="h-28 grid place-items-center"><Loader2 className="h-4 w-4 animate-spin" /></div>}
      <figcaption className="px-2 py-1 text-xs truncate">{im.legenda || im.tipo}</figcaption>
      <button type="button" onClick={() => onApagar(im)} className="absolute top-1 right-1 rounded bg-background/80 p-1 hover:text-destructive" aria-label="x">
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </figure>
  );
}

export default function FioProjeto({ pid, lang }) {
  const c = COPY[lang] || COPY.fr;
  const [est, setEst] = useState(null);
  const [busy, setBusy] = useState("");
  const [tipo, setTipo] = useState("bim");
  const [legenda, setLegenda] = useState("");
  const inputRef = useRef(null);
  const [zi, setZi] = useState("");
  const [zv, setZv] = useState("");
  const [term, setTerm] = useState(null);
  const pt = lang === "pt";

  const carregar = useCallback(() => {
    if (!pid) return;
    api.get(`/fio-projeto/${encodeURIComponent(pid)}`).then((r) => setEst(r.data)).catch(() => {});
  }, [pid]);
  useEffect(() => { carregar(); }, [carregar]);

  const juntar = async (file) => {
    if (!file) return;
    setBusy("img");
    try {
      const fd = new FormData();
      fd.append("file", file); fd.append("tipo", tipo); fd.append("legenda", legenda);
      await api.post(`/fio-projeto/${encodeURIComponent(pid)}/imagens`, fd);
      toast.success(c.juntada); setLegenda(""); carregar();
    } catch (e) { toast.error(e?.response?.data?.detail || c.erro); } finally { setBusy(""); }
  };
  const apagar = async (im) => {
    try { await api.delete(`/fio-projeto/${encodeURIComponent(pid)}/imagens/${im.imagem_id}`); carregar(); }
    catch { toast.error(c.erro); }
  };
  const dossier = async () => {
    setBusy("pdf");
    try {
      const r = await api.get(`/fio-projeto/${encodeURIComponent(pid)}/dossier.pdf`, { responseType: "blob", timeout: 240000 });
      const href = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = href; a.download = `Dossier-${(est?.projeto?.titulo || pid).replace(/[^\w.-]+/g, "_")}.pdf`; a.click();
      setTimeout(() => URL.revokeObjectURL(href), 4000);
      carregar();
    } catch { toast.error(c.erro); } finally { setBusy(""); }
  };

  const termica = async () => {
    setBusy("th");
    try {
      const { data } = await api.post(`/fio-projeto/${encodeURIComponent(pid)}/termica`, { zona_inverno: zi, zona_verao: zv }, { timeout: 120000 });
      setTerm(data); carregar();
    } catch (e) { toast.error(e?.response?.data?.detail || c.erro); } finally { setBusy(""); }
  };

  if (!pid) return null;
  return (
    <section className="surface rounded-2xl p-4 sm:p-5 space-y-4" data-testid="fio-projeto">
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold">{c.titulo}</h2>
          <p className="text-sm text-muted-foreground">{c.sub}</p>
        </div>
        <span className="ml-auto flex flex-wrap gap-2">
          <Button asChild data-testid="fio-assistente">
            <Link to={`/assistant?atelier=${encodeURIComponent(pid)}`}><MessageSquare className="h-4 w-4 mr-1" />{c.assistente}</Link>
          </Button>
          <Button variant="outline" onClick={dossier} disabled={busy === "pdf"} data-testid="fio-dossier">
            {busy === "pdf" ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <FileDown className="h-4 w-4 mr-1" />}{c.dossier}
          </Button>
        </span>
      </div>

      {est && (
        <ol className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-4">
          {est.etapas.map((e) => (
            <li key={e.etapa} className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-sm ${e.desatualizado ? "border-amber-500/60 bg-amber-50/60 dark:bg-amber-950/20" : "border-border"}`}
              data-testid={`fio-etapa-${e.etapa}`} title={e.desatualizado ? c.refazer : e.ref || ""}>
              {e.desatualizado ? <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
                : e.feito ? <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0 mt-0.5" /> : <Circle className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />}
              <span className="min-w-0">
                <span className="block">{e.nome}</span>
                {e.desatualizado && <span className="block text-xs text-amber-700">{c.refazer}</span>}
              </span>
            </li>
          ))}
        </ol>
      )}

      <div className="space-y-2 rounded-xl border border-border p-3" data-testid="fio-termica">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold mr-2 flex items-center gap-1"><Thermometer className="h-4 w-4" />{c.termica}</h3>
          {pt && (
            <>
              <select value={zi} onChange={(e) => setZi(e.target.value)} className="h-9 rounded-md border border-input bg-background px-2 text-sm" aria-label={c.zonaI}>
                <option value="">{c.zonaI}</option>{["I1", "I2", "I3"].map((z) => <option key={z} value={z}>{z}</option>)}
              </select>
              <select value={zv} onChange={(e) => setZv(e.target.value)} className="h-9 rounded-md border border-input bg-background px-2 text-sm" aria-label={c.zonaV}>
                <option value="">{c.zonaV}</option>{["V1", "V2", "V3"].map((z) => <option key={z} value={z}>{z}</option>)}
              </select>
            </>
          )}
          <Button variant="outline" size="sm" onClick={termica} disabled={busy === "th"} data-testid="fio-termica-calcular">
            {busy === "th" ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Thermometer className="h-4 w-4 mr-1" />}{c.termica}
          </Button>
          {term && <span className={`text-sm font-semibold ${term.estado === "cumpre" ? "text-emerald-700" : "text-amber-700"}`}>{term.resultado}</span>}
        </div>
        {term && (
          <div className="grid gap-3 md:grid-cols-2 text-sm">
            <ul className="space-y-1">
              {(term.verificacoes || []).map((v, i) => (
                <li key={i} className="flex gap-2"><span className="text-muted-foreground">{v.elemento}</span>
                  <span className="ml-auto whitespace-nowrap">{v.valor ?? "—"}{v.limite != null ? ` / ${v.limite}` : ""} · {v.estado}</span></li>
              ))}
            </ul>
            <div className="space-y-2">
              {!!term.indicacoes?.length && (<div><p className="font-semibold">{c.indicacoes}</p>
                <ul className="list-disc pl-5 space-y-0.5">{term.indicacoes.map((x, i) => <li key={i}>{x}</li>)}</ul></div>)}
              {!!term.dados_em_falta?.length && (<div><p className="font-semibold">{c.faltam}</p>
                <ul className="list-disc pl-5 space-y-0.5 text-muted-foreground">{term.dados_em_falta.map((f, i) => <li key={i}>{f.o_que}{f.materiais?.length ? ` : ${f.materiais.join(", ")}` : ""} — {f.onde}</li>)}</ul></div>)}
              <p className="text-xs text-muted-foreground">{term.aprovacao}</p>
            </div>
          </div>
        )}
      </div>

      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold mr-2">{c.imagens}</h3>
          <select value={tipo} onChange={(e) => setTipo(e.target.value)} className="h-9 rounded-md border border-input bg-background px-2 text-sm" data-testid="fio-tipo">
            {Object.entries(c.tipos).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <input value={legenda} onChange={(e) => setLegenda(e.target.value)} maxLength={200} placeholder={c.legenda}
            className="h-9 min-w-40 flex-1 rounded-md border border-input bg-background px-2 text-sm" />
          <Button variant="outline" size="sm" onClick={() => inputRef.current?.click()} disabled={busy === "img"} data-testid="fio-juntar">
            {busy === "img" ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <ImagePlus className="h-4 w-4 mr-1" />}{c.imagem}
          </Button>
          <input ref={inputRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
            onChange={(e) => { juntar(e.target.files?.[0]); e.target.value = ""; }} />
        </div>
        {est && (est.imagens.length
          ? <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2">{est.imagens.map((im) => <Miniatura key={im.imagem_id} pid={pid} im={im} onApagar={apagar} />)}</div>
          : <p className="text-xs text-muted-foreground">{c.vazio}</p>)}
      </div>
    </section>
  );
}
