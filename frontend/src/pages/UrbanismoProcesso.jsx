import { useEffect, useState, useCallback } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowLeft, FileDown, Upload, Check, Loader2, Sparkles, ShieldCheck, FileText, Building2, Plus, Trash2,
  Scale, MapPin, Ruler, ListChecks, AlertTriangle, CheckCircle2, Circle, Info,
} from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const EDIFICIO = ["moradia_nova", "ampliacao", "anexo"];
const VOL_DEF = { shape: "rectangle", plot_l_m: 20, plot_w_m: 15, footprint_l_m: 10, footprint_w_m: 8, wing_l_m: 0, wing_w_m: 0, levels: 2,
  storey_h_m: 2.8, espessura_laje_m: 0.3, total_h_m: 0, roof_type: "duas_aguas", setback_front_m: 5, setback_side_m: 3, blocks: [],
  uso: "habitacao", n_fogos: 1, lugares_previstos: "", area_construcao_m2: "", distancia_alinhamento_fronteiro_m: "" };
const RES = {
  conforme: { label: "Conforme", cls: "text-emerald-700 bg-emerald-50 dark:bg-emerald-950/30", Icon: CheckCircle2 },
  nao_conforme: { label: "Não conforme", cls: "text-red-700 bg-red-50 dark:bg-red-950/30", Icon: AlertTriangle },
  atencao: { label: "Atenção", cls: "text-amber-700 bg-amber-50 dark:bg-amber-950/30", Icon: AlertTriangle },
  sem_dados: { label: "Sem dados", cls: "text-muted-foreground bg-muted", Icon: Circle },
  informativo: { label: "Informativo", cls: "text-slate-600 bg-slate-50 dark:bg-slate-900/40", Icon: Info },
};
const STATUS_FONTE = { confirmado: "confirmado", a_confirmar: "a confirmar", parametro_utilizador: "plano municipal" };
const DESENHOS = { PLANTA_IMPLANTACAO: ["planta-implantacao", "Planta de implantação"], CORTES: ["corte", "Corte"], ALCADOS: ["alcado", "Alçado"], AXONOMETRIA: ["axonometria", "Axonometria"] };

const pt = (v, nd = 2) => (v === null || v === undefined || v === "" ? "—" : typeof v === "number" ? v.toLocaleString("pt-PT", { maximumFractionDigits: nd }) : String(v));
const numOrNull = (v) => (v === "" || v === null || v === undefined || Number.isNaN(Number(v)) ? null : Number(v));

function filenameFromResponse(res, fallback) {
  const cd = res?.headers?.["content-disposition"] || "";
  const m = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(cd);
  try { return m ? decodeURIComponent(m[1] || m[2]) : fallback; } catch { return fallback; }
}

// Imagem autenticada (pedido com o cookie de sessão via axios) — evita depender de cookies em <img>.
function AuthImage({ path, ts, alt, testid }) {
  const [url, setUrl] = useState(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    let u = null; let alive = true;
    setErr(false);
    api.get(path, { responseType: "blob" }).then((r) => { if (!alive) return; u = URL.createObjectURL(r.data); setUrl(u); }).catch(() => alive && setErr(true));
    return () => { alive = false; if (u) URL.revokeObjectURL(u); };
  }, [path, ts]);
  if (err) return <p className="text-xs text-muted-foreground border rounded p-3">{alt}: desenho indisponível.</p>;
  if (!url) return <div className="h-40 grid place-items-center border rounded"><Loader2 className="h-4 w-4 animate-spin" /></div>;
  return <a href={url} target="_blank" rel="noreferrer"><img src={url} alt={alt} className="rounded border w-full" data-testid={testid} /></a>;
}

function Field({ label, unit, children }) {
  return <label className="grid gap-1 text-xs">{label}{unit ? ` (${unit})` : ""}{children}</label>;
}

export default function UrbanismoProcesso() {
  const { id } = useParams();
  const nav = useNavigate();
  const [cfg, setCfg] = useState(null);
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState("");
  const [ts, setTs] = useState(Date.now());
  const [dados, setDados] = useState({ requerente: {}, terreno: {}, enquadramento: {} });
  const [pdm, setPdm] = useState({});
  const [vol, setVol] = useState(VOL_DEF);
  const [params, setParams] = useState({});
  const [memoria, setMemoria] = useState("");
  const [tec, setTec] = useState({ tecnico_nome: "", tecnico_email: "", mensagem: "" });

  useEffect(() => { api.get("/urbanismo/config").then((r) => setCfg(r.data)).catch(() => {}); }, []);

  const apply = useCallback((data) => {
    setD(data);
    setDados({ requerente: data.requerente || {}, terreno: data.terreno || {}, enquadramento: data.enquadramento || {} });
    setPdm(data.pdm || {});
    setParams(data.parametros || {});
    setMemoria(data.memoria_texto || "");
    if (data.volume) setVol({ ...VOL_DEF, ...data.volume, blocks: data.volume.blocks || [] });
  }, []);

  const load = useCallback(async () => {
    try { const { data } = await api.get(`/urbanismo/processos/${id}`); apply(data); }
    catch { toast.error("Processo não encontrado."); nav("/urbanismo"); }
  }, [id, nav, apply]);
  useEffect(() => { load(); }, [load]);

  const patch = async (body, msg, key = "patch") => {
    setBusy(key);
    try { const { data } = await api.patch(`/urbanismo/processos/${id}`, body); apply(data); setTs(Date.now()); if (msg) toast.success(msg); return true; }
    catch (e) { const det = e?.response?.data?.detail; toast.error(Array.isArray(det) ? "Valores inválidos — verifique os campos." : det || "Gravação impossível."); return false; }
    finally { setBusy(""); }
  };

  const saveVolume = async () => {
    setBusy("volume");
    const body = { ...vol, levels: Number(vol.levels) || 1, n_fogos: numOrNull(vol.n_fogos), lugares_previstos: numOrNull(vol.lugares_previstos),
      area_construcao_m2: numOrNull(vol.area_construcao_m2), distancia_alinhamento_fronteiro_m: numOrNull(vol.distancia_alinhamento_fronteiro_m),
      blocks: (vol.blocks || []).map((b) => ({ name: b.name || "Anexo", l_m: Number(b.l_m) || 1, w_m: Number(b.w_m) || 1, x_m: Number(b.x_m) || 0, y_m: Number(b.y_m) || 0, h_m: numOrNull(b.h_m) })) };
    try { const { data } = await api.post(`/urbanismo/processos/${id}/volume`, body); apply(data); setTs(Date.now()); toast.success("Volumes gravados — peças desenhadas e verificação atualizadas."); }
    catch (e) { const det = e?.response?.data?.detail; toast.error(Array.isArray(det) ? "Valores fora dos limites — verifique as dimensões." : det || "Gravação impossível."); }
    finally { setBusy(""); }
  };

  const dl = async (path, fallback) => {
    setBusy(path);
    try {
      const res = await api.get(path, { responseType: "blob", timeout: 120000 });
      const u = URL.createObjectURL(res.data); const a = document.createElement("a");
      a.href = u; a.download = filenameFromResponse(res, fallback); a.click(); setTimeout(() => URL.revokeObjectURL(u), 1000);
    } catch (e) { toast.error(e?.response?.status === 422 ? "Defina primeiro os volumes." : "Transferência indisponível."); }
    finally { setBusy(""); }
  };

  const upload = async (code, file) => {
    if (!file) return;
    if (file.size > 25 * 1024 * 1024) return toast.error("Ficheiro demasiado grande (máx. 25 MB).");
    setBusy(`peca-${code}`);
    const fd = new FormData(); fd.append("file", file);
    try { await api.post(`/urbanismo/processos/${id}/pecas/${code}`, fd); toast.success("Peça carregada."); await load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Carregamento impossível."); }
    finally { setBusy(""); }
  };
  const removePeca = async (code) => { try { await api.delete(`/urbanismo/processos/${id}/pecas/${code}`); await load(); } catch { toast.error("Remoção impossível."); } };

  const genMemoria = async () => {
    setBusy("memoria");
    try { const { data } = await api.post(`/urbanismo/processos/${id}/memoria`, {}, { timeout: 120000 }); setMemoria(data.memoria_texto); toast.success("Memória redigida — reveja e edite antes de exportar."); }
    catch { toast.error("Redação indisponível — escreva a memória manualmente."); }
    finally { setBusy(""); }
  };

  const pedirValidacao = async () => {
    if (tec.tecnico_nome.trim().length < 2 || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(tec.tecnico_email)) return toast.error("Indique o nome e o e-mail do técnico.");
    setBusy("validacao");
    try { const { data } = await api.post(`/urbanismo/processos/${id}/validacao`, tec); toast.success(data.email_sent ? "Pedido enviado ao técnico." : "Ligação criada — envie-a ao técnico."); await load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Pedido impossível."); }
    finally { setBusy(""); }
  };

  const remover = async () => {
    if (!window.confirm("Eliminar este processo?")) return;
    try { await api.delete(`/urbanismo/processos/${id}`); nav("/urbanismo"); } catch { toast.error("Eliminação impossível."); }
  };

  if (!d) return <div className="p-8 flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> A carregar…</div>;
  const verif = d.verificacao || {};
  const rj = verif.rjue || {};
  const q = verif.quadro;
  const tipo = d.tipo_obra;
  const isEdif = EDIFICIO.includes(tipo);
  const hasDrawings = !isEdif || !!d.volume;
  const camposPdm = (cfg?.pdm_campos || []).filter((c) => c.tipos.includes(tipo));
  const setT = (k, v) => setDados((x) => ({ ...x, terreno: { ...x.terreno, [k]: v } }));
  const setR = (k, v) => setDados((x) => ({ ...x, requerente: { ...x.requerente, [k]: v } }));
  const setE = (k, v) => setDados((x) => ({ ...x, enquadramento: { ...x.enquadramento, [k]: v } }));
  const setV = (k, v) => setVol((x) => ({ ...x, [k]: v }));
  const setP = (k, v) => setParams((x) => ({ ...x, [k]: v }));
  const updBlock = (i, k, v) => setVol((x) => ({ ...x, blocks: x.blocks.map((b, j) => (j === i ? { ...b, [k]: v } : b)) }));
  const drawingCodes = Object.keys(DESENHOS).filter((c) => (tipo === "piscina" ? ["PLANTA_IMPLANTACAO", "CORTES"].includes(c) : tipo === "muro" ? c !== "AXONOMETRIA" : true));
  const procCls = rj.procedimento === "isento" ? "border-emerald-500 bg-emerald-50 dark:bg-emerald-950/20" : rj.procedimento === "comunicacao_previa" ? "border-blue-500 bg-blue-50 dark:bg-blue-950/20" : "border-amber-500 bg-amber-50 dark:bg-amber-950/20";

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 grid gap-5" data-testid="urb-processo-page">
      <button onClick={() => nav("/urbanismo")} className="flex items-center gap-1 text-sm text-muted-foreground w-fit" data-testid="urb-voltar"><ArrowLeft className="h-4 w-4" /> Os meus processos</button>
      <header className="grid gap-1">
        <h1 className="text-2xl font-bold tracking-tight" data-testid="urb-processo-title">{d.title}</h1>
        <p className="text-sm text-muted-foreground">{d.tipo_obra_label}{d.terreno?.concelho ? ` · ${d.terreno.concelho}` : ""}</p>
      </header>

      {/* Procedimento RJUE (motor existente) */}
      <section className={`rounded-lg border p-4 grid gap-1 ${procCls}`} data-testid="urb-rjue">
        <p className="text-xs uppercase tracking-wide text-muted-foreground flex items-center gap-1"><Scale className="h-3.5 w-3.5" /> Enquadramento RJUE (DL 555/99) — indicativo</p>
        <h2 className="text-lg font-bold" data-testid="urb-procedimento">{cfg?.procedimentos?.[rj.procedimento] || rj.procedimento}</h2>
        <p className="text-sm">{rj.fundamento_legal}</p>
        {rj.tecnicos_obrigatorios?.length > 0 && <p className="text-xs">Técnicos indicativos: {rj.tecnicos_obrigatorios.map((t) => t.replace(/_/g, " ")).join(", ")}.</p>}
        {rj.referencias_legais?.length > 0 && <p className="text-xs">Referências: {rj.referencias_legais.map((r, i) => <a key={i} href={r.url} target="_blank" rel="noreferrer" className="underline mr-2">art.º {r.artigo}</a>)}</p>}
        <p className="text-xs mt-1">Para o requerimento, a ficha estatística e a <b>subscrição por técnico (termo de responsabilidade)</b>, continue em <Link to={cfg?.pagina_rjue || "/particulares/autorizacao-obras"} className="underline font-medium" data-testid="urb-link-rjue">Autorização de obras</Link>.</p>
      </section>

      {/* Dados do processo */}
      <section className="border rounded-lg p-4 grid gap-3" data-testid="urb-dados">
        <h2 className="font-semibold flex items-center gap-2"><MapPin className="h-4 w-4 text-primary" /> Requerente, terreno e enquadramento</h2>
        <div className="grid sm:grid-cols-3 gap-2">
          <Field label="Requerente"><Input className="h-9" value={dados.requerente.nome || ""} onChange={(e) => setR("nome", e.target.value)} data-testid="urb-req-nome" /></Field>
          <Field label="NIF"><Input className="h-9" value={dados.requerente.nif || ""} onChange={(e) => setR("nif", e.target.value)} /></Field>
          <Field label="E-mail"><Input className="h-9" value={dados.requerente.email || ""} onChange={(e) => setR("email", e.target.value)} /></Field>
          <Field label="Morada da obra"><Input className="h-9" value={dados.terreno.morada || ""} onChange={(e) => setT("morada", e.target.value)} data-testid="urb-ter-morada" /></Field>
          <Field label="Código postal"><Input className="h-9" value={dados.terreno.codigo_postal || ""} onChange={(e) => setT("codigo_postal", e.target.value)} /></Field>
          <Field label="Concelho"><Input className="h-9" value={dados.terreno.concelho || ""} onChange={(e) => setT("concelho", e.target.value)} /></Field>
          <Field label="Freguesia"><Input className="h-9" value={dados.terreno.freguesia || ""} onChange={(e) => setT("freguesia", e.target.value)} /></Field>
          <Field label="Artigo matricial"><Input className="h-9" value={dados.terreno.artigo_matricial || ""} onChange={(e) => setT("artigo_matricial", e.target.value)} /></Field>
          <Field label="Descrição predial"><Input className="h-9" value={dados.terreno.descricao_predial || ""} onChange={(e) => setT("descricao_predial", e.target.value)} /></Field>
          <Field label="Área do terreno" unit="m²"><Input className="h-9" type="number" value={dados.terreno.area_terreno_m2 ?? ""} onChange={(e) => setT("area_terreno_m2", numOrNull(e.target.value))} data-testid="urb-ter-area" /></Field>
          {["ampliacao", "piscina"].includes(tipo) && <Field label={tipo === "piscina" ? "Área de construção da edificação principal" : "Área de construção existente"} unit="m²"><Input className="h-9" type="number" value={dados.enquadramento.area_construcao_existente_m2 ?? ""} onChange={(e) => setE("area_construcao_existente_m2", numOrNull(e.target.value))} data-testid="urb-existente" /></Field>}
        </div>
        <div className="grid sm:grid-cols-2 gap-1 text-xs">
          {[["confina_via_publica", "Confina com a via pública"], ["tem_edificacao_principal", "Existe edificação principal legalizada"], ["tem_pdm_com_parametros", "Área com plano de pormenor / unidade de execução com parâmetros definidos"],
            ["tem_loteamento_pip", "Lote de loteamento / PIP favorável"], ["zona_urbana_consolidada", "Zona urbana consolidada"], ["zona_protegida", "Zona de proteção de património"], ["imovel_classificado", "Imóvel classificado ou em vias de classificação"]].map(([k, l]) => (
            <label key={k} className="flex items-center gap-2"><input type="checkbox" checked={!!dados.enquadramento[k]} onChange={(e) => setE(k, e.target.checked)} data-testid={`urb-enq-${k}`} /> {l}</label>
          ))}
        </div>
        <Button onClick={() => patch(dados, "Dados gravados.", "dados")} disabled={busy === "dados"} variant="outline" className="w-fit" data-testid="urb-dados-save">{busy === "dados" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} Gravar dados</Button>
      </section>

      {/* Parâmetros municipais */}
      <section className="border rounded-lg p-4 grid gap-3" data-testid="urb-pdm">
        <h2 className="font-semibold flex items-center gap-2"><FileText className="h-4 w-4 text-primary" /> Parâmetros do plano municipal (PDM / PP / loteamento)</h2>
        <p className="text-xs text-muted-foreground">Introduza os valores do regulamento aplicável ao seu terreno. A ConstruPilot nunca preenche valores municipais: um campo vazio fica «sem dados» na verificação.</p>
        <div className="grid sm:grid-cols-3 gap-2">
          <Field label="Plano aplicável"><Input className="h-9" value={pdm.plano || ""} onChange={(e) => setPdm({ ...pdm, plano: e.target.value })} placeholder="Ex.: PDM de …, 1.ª revisão" data-testid="urb-pdm-plano" /></Field>
          <Field label="Classe / categoria de espaço"><Input className="h-9" value={pdm.classe_espaco || ""} onChange={(e) => setPdm({ ...pdm, classe_espaco: e.target.value })} /></Field>
          <Field label="Artigos do regulamento"><Input className="h-9" value={pdm.fonte_artigos || ""} onChange={(e) => setPdm({ ...pdm, fonte_artigos: e.target.value })} /></Field>
          {camposPdm.map((c) => (
            <Field key={c.key} label={c.label} unit={c.unit}><Input className="h-9" type="number" step="any" value={pdm[c.key] ?? ""} onChange={(e) => setPdm({ ...pdm, [c.key]: numOrNull(e.target.value) })} data-testid={`urb-pdm-${c.key}`} /></Field>
          ))}
        </div>
        <Button onClick={() => patch({ pdm }, "Parâmetros gravados — verificação atualizada.", "pdm")} disabled={busy === "pdm"} className="w-fit" data-testid="urb-pdm-save">{busy === "pdm" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} Gravar e verificar</Button>
      </section>

      {/* Editor de volumes (construções) */}
      {isEdif && (
        <section className="border rounded-lg p-4 grid gap-3" data-testid="urb-volumes">
          <h2 className="font-semibold flex items-center gap-2"><Building2 className="h-4 w-4 text-primary" /> Editor de volumes</h2>
          <p className="text-xs text-muted-foreground">Terreno retangular: frente (via pública) × profundidade. A construção é colocada pelos afastamentos frontal e lateral esquerdo.</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <Field label="Forma"><select className="h-9 rounded-md border bg-background px-2 text-sm" value={vol.shape} onChange={(e) => setV("shape", e.target.value)} data-testid="urb-vol-shape"><option value="rectangle">Retângulo</option><option value="L">Em L</option><option value="T">Em T</option></select></Field>
            <Field label="Terreno — frente" unit="m"><Input className="h-9" type="number" value={vol.plot_l_m} onChange={(e) => setV("plot_l_m", Number(e.target.value))} data-testid="urb-vol-plot-l" /></Field>
            <Field label="Terreno — profundidade" unit="m"><Input className="h-9" type="number" value={vol.plot_w_m} onChange={(e) => setV("plot_w_m", Number(e.target.value))} data-testid="urb-vol-plot-w" /></Field>
            <Field label="Uso"><select className="h-9 rounded-md border bg-background px-2 text-sm" value={vol.uso} onChange={(e) => setV("uso", e.target.value)} data-testid="urb-vol-uso">{Object.entries(cfg?.usos || { habitacao: "Habitação", comercio: "Comércio / serviços", apoio: "Apoio não habitável" }).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
            <Field label="Construção — largura (frente)" unit="m"><Input className="h-9" type="number" value={vol.footprint_l_m} onChange={(e) => setV("footprint_l_m", Number(e.target.value))} data-testid="urb-vol-l" /></Field>
            <Field label="Construção — profundidade" unit="m"><Input className="h-9" type="number" value={vol.footprint_w_m} onChange={(e) => setV("footprint_w_m", Number(e.target.value))} data-testid="urb-vol-w" /></Field>
            {vol.shape !== "rectangle" && <>
              <Field label={vol.shape === "T" ? "Corpo central — largura" : "Recorte — largura"} unit="m"><Input className="h-9" type="number" value={vol.wing_l_m} onChange={(e) => setV("wing_l_m", Number(e.target.value))} /></Field>
              <Field label={vol.shape === "T" ? "Corpo do tardoz — profundidade" : "Recorte — profundidade"} unit="m"><Input className="h-9" type="number" value={vol.wing_w_m} onChange={(e) => setV("wing_w_m", Number(e.target.value))} /></Field>
            </>}
            <Field label="Afastamento frontal" unit="m"><Input className="h-9" type="number" value={vol.setback_front_m} onChange={(e) => setV("setback_front_m", Number(e.target.value))} data-testid="urb-vol-sf" /></Field>
            <Field label="Afastamento lateral esquerdo" unit="m"><Input className="h-9" type="number" value={vol.setback_side_m} onChange={(e) => setV("setback_side_m", Number(e.target.value))} data-testid="urb-vol-ss" /></Field>
            <Field label="N.º de pisos acima do solo"><Input className="h-9" type="number" value={vol.levels} onChange={(e) => setV("levels", Number(e.target.value))} data-testid="urb-vol-levels" /></Field>
            <Field label="Altura piso a piso" unit="m"><Input className="h-9" type="number" step="0.05" value={vol.storey_h_m} onChange={(e) => setV("storey_h_m", Number(e.target.value))} data-testid="urb-vol-storey" /></Field>
            <Field label="Laje + revestimentos" unit="m"><Input className="h-9" type="number" step="0.01" value={vol.espessura_laje_m} onChange={(e) => setV("espessura_laje_m", Number(e.target.value))} /></Field>
            <Field label="Cobertura"><select className="h-9 rounded-md border bg-background px-2 text-sm" value={vol.roof_type} onChange={(e) => setV("roof_type", e.target.value)} data-testid="urb-vol-roof">{Object.entries(cfg?.coberturas || { duas_aguas: "Duas águas", uma_agua: "Uma água", plana: "Cobertura plana" }).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
            <Field label="Altura total (0 = automática)" unit="m"><Input className="h-9" type="number" value={vol.total_h_m} onChange={(e) => setV("total_h_m", Number(e.target.value))} /></Field>
            {tipo !== "anexo" && <>
              <Field label="N.º de fogos"><Input className="h-9" type="number" value={vol.n_fogos ?? ""} onChange={(e) => setV("n_fogos", e.target.value)} /></Field>
              <Field label="Lugares de estacionamento previstos"><Input className="h-9" type="number" value={vol.lugares_previstos ?? ""} onChange={(e) => setV("lugares_previstos", e.target.value)} data-testid="urb-vol-lugares" /></Field>
            </>}
            <Field label="Área de construção (se diferente do cálculo)" unit="m²"><Input className="h-9" type="number" value={vol.area_construcao_m2 ?? ""} onChange={(e) => setV("area_construcao_m2", e.target.value)} /></Field>
            <Field label="Distância ao alinhamento fronteiro (facultativo)" unit="m"><Input className="h-9" type="number" value={vol.distancia_alinhamento_fronteiro_m ?? ""} onChange={(e) => setV("distancia_alinhamento_fronteiro_m", e.target.value)} /></Field>
          </div>
          <div className="grid gap-2" data-testid="urb-vol-blocks">
            <div className="flex items-center justify-between"><span className="text-xs font-medium">Anexos (garagem, telheiro, arrumos…)</span>
              <Button type="button" variant="outline" size="sm" className="h-7 text-xs" onClick={() => setVol((x) => ({ ...x, blocks: [...(x.blocks || []), { name: "Anexo", l_m: 4, w_m: 3, x_m: 1, y_m: 1, h_m: 2.4 }] }))} data-testid="urb-vol-add-block"><Plus className="h-3 w-3" /> Adicionar</Button></div>
            {(vol.blocks || []).map((b, i) => (
              <div key={i} className="grid grid-cols-3 sm:grid-cols-7 gap-1 items-end text-[11px] border rounded p-2">
                <Field label="Nome"><Input className="h-8" value={b.name} onChange={(e) => updBlock(i, "name", e.target.value)} /></Field>
                <Field label="Largura (m)"><Input className="h-8" type="number" value={b.l_m} onChange={(e) => updBlock(i, "l_m", e.target.value)} /></Field>
                <Field label="Profund. (m)"><Input className="h-8" type="number" value={b.w_m} onChange={(e) => updBlock(i, "w_m", e.target.value)} /></Field>
                <Field label="X (m)"><Input className="h-8" type="number" value={b.x_m} onChange={(e) => updBlock(i, "x_m", e.target.value)} /></Field>
                <Field label="Y (m)"><Input className="h-8" type="number" value={b.y_m} onChange={(e) => updBlock(i, "y_m", e.target.value)} /></Field>
                <Field label="Altura (m)"><Input className="h-8" type="number" value={b.h_m ?? ""} onChange={(e) => updBlock(i, "h_m", e.target.value)} /></Field>
                <Button type="button" variant="ghost" size="icon" className="h-8 w-8 text-red-600" onClick={() => setVol((x) => ({ ...x, blocks: x.blocks.filter((_, j) => j !== i) }))}><Trash2 className="h-4 w-4" /></Button>
              </div>
            ))}
            <p className="text-[11px] text-muted-foreground">X = distância ao limite lateral esquerdo; Y = distância à frente do terreno.</p>
          </div>
          <Button onClick={saveVolume} disabled={busy === "volume"} className="w-fit" data-testid="urb-vol-save">{busy === "volume" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Ruler className="h-4 w-4" />} Gerar peças desenhadas e verificar</Button>
        </section>
      )}

      {/* Muro / piscina */}
      {!isEdif && (
        <section className="border rounded-lg p-4 grid gap-3" data-testid="urb-parametros">
          <h2 className="font-semibold flex items-center gap-2"><Ruler className="h-4 w-4 text-primary" /> Características {tipo === "muro" ? "do muro" : "da piscina"}</h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {tipo === "muro" ? <>
              <Field label="Comprimento" unit="m"><Input className="h-9" type="number" value={params.comprimento_m ?? ""} onChange={(e) => setP("comprimento_m", numOrNull(e.target.value))} data-testid="urb-p-comprimento" /></Field>
              <Field label="Altura" unit="m"><Input className="h-9" type="number" value={params.altura_m ?? ""} onChange={(e) => setP("altura_m", numOrNull(e.target.value))} data-testid="urb-p-altura" /></Field>
              <Field label="Tipo"><select className="h-9 rounded-md border bg-background px-2 text-sm" value={params.subtipo || "vedacao"} onChange={(e) => setP("subtipo", e.target.value)}><option value="vedacao">Muro de vedação</option><option value="suporte">Muro de suporte de terras</option></select></Field>
              <Field label="Implantação"><select className="h-9 rounded-md border bg-background px-2 text-sm" value={params.implantacao || "frente"} onChange={(e) => setP("implantacao", e.target.value)}>{Object.entries(cfg?.implantacoes_muro || {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
              <Field label="Material"><select className="h-9 rounded-md border bg-background px-2 text-sm" value={params.material || ""} onChange={(e) => setP("material", e.target.value)}><option value="">—</option>{Object.entries(cfg?.materiais_muro || {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
              <Field label="Largura do portão" unit="m"><Input className="h-9" type="number" value={params.portao_largura_m ?? ""} onChange={(e) => setP("portao_largura_m", numOrNull(e.target.value))} /></Field>
              <Field label="Posição do portão (desde o canto)" unit="m"><Input className="h-9" type="number" value={params.portao_posicao_m ?? ""} onChange={(e) => setP("portao_posicao_m", numOrNull(e.target.value))} /></Field>
              <div className="grid gap-1 text-xs content-end">
                <label className="flex items-center gap-2"><input type="checkbox" checked={!!params.portao} onChange={(e) => setP("portao", e.target.checked)} /> Portão</label>
                <label className="flex items-center gap-2"><input type="checkbox" checked={!!params.capeamento} onChange={(e) => setP("capeamento", e.target.checked)} /> Capeamento</label>
              </div>
            </> : <>
              <Field label="Comprimento do tanque" unit="m"><Input className="h-9" type="number" value={params.comprimento_m ?? ""} onChange={(e) => setP("comprimento_m", numOrNull(e.target.value))} data-testid="urb-p-comprimento" /></Field>
              <Field label="Largura do tanque" unit="m"><Input className="h-9" type="number" value={params.largura_m ?? ""} onChange={(e) => setP("largura_m", numOrNull(e.target.value))} /></Field>
              <Field label="Profundidade" unit="m"><Input className="h-9" type="number" value={params.profundidade_m ?? ""} onChange={(e) => setP("profundidade_m", numOrNull(e.target.value))} /></Field>
              <Field label="Distância aos limites" unit="m"><Input className="h-9" type="number" value={params.distancia_limites_m ?? ""} onChange={(e) => setP("distancia_limites_m", numOrNull(e.target.value))} /></Field>
              <Field label="Altura da cobertura" unit="m"><Input className="h-9" type="number" value={params.cobertura_h_m ?? ""} onChange={(e) => setP("cobertura_h_m", numOrNull(e.target.value))} /></Field>
              <label className="flex items-center gap-2 text-xs content-end"><input type="checkbox" checked={!!params.cobertura} onChange={(e) => setP("cobertura", e.target.checked)} /> Cobertura amovível</label>
            </>}
          </div>
          <Button onClick={() => patch({ parametros: Object.fromEntries(Object.entries(params).filter(([, v]) => v !== null && v !== "")) }, "Características gravadas.", "params")} disabled={busy === "params"} className="w-fit" data-testid="urb-params-save">{busy === "params" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Ruler className="h-4 w-4" />} Gravar e gerar desenhos</Button>
        </section>
      )}

      {/* Peças desenhadas */}
      {hasDrawings && (
        <section className="border rounded-lg p-4 grid gap-3" data-testid="urb-desenhos">
          <h2 className="font-semibold flex items-center gap-2"><Building2 className="h-4 w-4 text-primary" /> Peças desenhadas (esquemáticas)</h2>
          <div className="grid sm:grid-cols-2 gap-2">
            {drawingCodes.map((c) => <AuthImage key={c} path={`/urbanismo/processos/${id}/desenhos/${DESENHOS[c][0]}.png`} ts={ts} alt={DESENHOS[c][1]} testid={`urb-desenho-${DESENHOS[c][0]}`} />)}
          </div>
          <p className="text-[11px] text-muted-foreground">Desenhos determinísticos a partir das dimensões introduzidas — a verificar, cotar e assinar por técnico habilitado. Sem fundo cadastral: carregue a planta de localização e o levantamento topográfico nas peças.</p>
        </section>
      )}

      {/* Verificação */}
      <section className="border rounded-lg p-4 grid gap-3" data-testid="urb-verificacao">
        <h2 className="font-semibold flex items-center gap-2"><ListChecks className="h-4 w-4 text-primary" /> Quadro de áreas e verificação</h2>
        {q && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs" data-testid="urb-quadro">
            {[["Área do terreno", `${pt(q.area_terreno_m2)} m²`], ["Área de implantação", `${pt(q.area_implantacao_m2)} m²`], ["Área de construção", `${pt(q.area_construcao_m2)} m²`],
              ["Índice de ocupação", `${pt(q.indice_ocupacao_pct, 1)} %`], ["Índice de utilização", pt(q.indice_utilizacao, 3)], ["Pisos", q.n_pisos],
              ["Altura da fachada", `${pt(q.altura_fachada_m)} m`], ["Altura total", `${pt(q.altura_total_m)} m`]].map(([k, v]) => (
              <div key={k} className="border rounded-md p-2"><span className="text-muted-foreground">{k}</span><p className="text-base font-semibold">{v}</p></div>
            ))}
          </div>
        )}
        <div className="grid gap-1">
          {(verif.verificacoes || []).map((it) => {
            const r = RES[it.resultado] || RES.informativo;
            return (
              <div key={it.codigo} className="border rounded-md p-2 text-xs grid sm:grid-cols-[1fr_auto] gap-1" data-testid={`urb-check-${it.codigo}`}>
                <div>
                  <p className="font-medium text-sm">{it.titulo}</p>
                  <p>Projeto: <b>{pt(it.valor)}{it.valor !== null && it.unidade ? ` ${it.unidade}` : ""}</b> · Limite: <b>{pt(it.limite)}{it.limite !== null && it.unidade ? ` ${it.unidade}` : ""}</b></p>
                  {it.nota && <p className="text-muted-foreground">{it.nota}</p>}
                  <p className="text-muted-foreground">Fonte: {it.fonte.diploma}{it.fonte.artigo ? ` — ${it.fonte.artigo}` : ""} [{STATUS_FONTE[it.fonte.status] || it.fonte.status}]</p>
                </div>
                <span className={`h-fit inline-flex items-center gap-1 rounded px-2 py-1 font-medium ${r.cls}`}><r.Icon className="h-3.5 w-3.5" /> {r.label}</span>
              </div>
            );
          })}
        </div>
        {verif.parametros_em_falta?.length > 0 && <p className="text-xs text-muted-foreground">Parâmetros municipais não indicados: {verif.parametros_em_falta.join("; ")}.</p>}
        {verif.valores_a_confirmar?.length > 0 && <div className="text-xs bg-amber-50 dark:bg-amber-950/20 border border-amber-300 rounded p-2"><b>Valores a confirmar:</b><ul className="list-disc pl-4">{verif.valores_a_confirmar.map((x) => <li key={x}>{x}</li>)}</ul></div>}
      </section>

      {/* Memória descritiva */}
      <section className="border rounded-lg p-4 grid gap-2" data-testid="urb-memoria">
        <h2 className="font-semibold flex items-center gap-2"><FileText className="h-4 w-4 text-primary" /> Memória descritiva</h2>
        <textarea rows={6} className="rounded-md border bg-background p-2 text-sm" value={memoria} onChange={(e) => setMemoria(e.target.value)} placeholder="Escreva ou peça uma proposta de redação (opcional). Sem texto, a exportação usa um texto neutro a completar." data-testid="urb-memoria-text" />
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={genMemoria} disabled={busy === "memoria"} data-testid="urb-memoria-ia">{busy === "memoria" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Propor redação (IA, opcional)</Button>
          <Button variant="outline" onClick={() => patch({ memoria_texto: memoria }, "Memória gravada.", "mem")} disabled={busy === "mem"} data-testid="urb-memoria-save"><Check className="h-4 w-4" /> Gravar texto</Button>
        </div>
      </section>

      {/* Peças do processo */}
      <section className="border rounded-lg p-4 grid gap-2" data-testid="urb-pecas">
        <h2 className="font-semibold">Peças do processo <span className="text-xs text-muted-foreground">({(d.checklist?.items || []).filter((i) => i.ok).length}/{(d.checklist?.items || []).length})</span></h2>
        {(d.checklist?.items || []).map((it) => (
          <div key={it.code} className="flex items-center gap-2 text-sm border-b last:border-0 py-2" data-testid={`urb-peca-${it.code}`}>
            {it.ok ? <Check className="h-4 w-4 text-emerald-600 shrink-0" /> : <span className="h-4 w-4 rounded-full border shrink-0" />}
            <div className="flex-1">{it.label}{!it.required && <span className="text-xs text-muted-foreground"> (complementar)</span>}{it.gerada && <span className="text-xs text-muted-foreground"> — gerada automaticamente</span>}</div>
            {it.carregada && <Button size="sm" variant="ghost" className="h-7 text-xs text-red-600" onClick={() => removePeca(it.code)}>Remover</Button>}
            <label className="shrink-0">
              <input type="file" accept="application/pdf,image/png,image/jpeg,image/webp" className="hidden" onChange={(e) => upload(it.code, e.target.files?.[0])} data-testid={`urb-upload-${it.code}`} />
              <span className="inline-flex items-center gap-1 px-2 py-1 rounded border cursor-pointer hover:bg-muted text-xs">{busy === `peca-${it.code}` ? <Loader2 className="h-3 w-3 animate-spin" /> : <Upload className="h-3 w-3" />} {it.carregada ? "Substituir" : it.origem === "auto" ? "Substituir pela sua" : "Carregar"}</span>
            </label>
          </div>
        ))}
        <p className="text-[11px] text-muted-foreground">{d.checklist?.fonte?.diploma} — lista indicativa, confirmar com o município.</p>
      </section>

      {/* Exportação */}
      <section className="flex flex-col sm:flex-row flex-wrap gap-2" data-testid="urb-export">
        <Button onClick={() => dl(`/urbanismo/processos/${id}/quadro.pdf`, "quadro-areas.pdf")} disabled={!!busy || !hasDrawings} data-testid="urb-dl-quadro"><FileText className="h-4 w-4" /> Quadro de áreas (PDF)</Button>
        <Button onClick={() => dl(`/urbanismo/processos/${id}/pecas-desenhadas.pdf`, "pecas-desenhadas.pdf")} disabled={!!busy || !hasDrawings} variant="outline" data-testid="urb-dl-pecas"><FileDown className="h-4 w-4" /> Peças desenhadas (PDF A3)</Button>
        <Button onClick={() => dl(`/urbanismo/processos/${id}/export.zip`, "processo-urbanismo.zip")} disabled={!!busy || !hasDrawings} variant="outline" data-testid="urb-dl-zip"><FileDown className="h-4 w-4" /> Processo completo (ZIP)</Button>
      </section>

      {/* Validação por técnico */}
      <section className="border rounded-lg p-4 grid gap-2" data-testid="urb-validacao">
        <h2 className="font-semibold flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-primary" /> Revisão por técnico (arquiteto / engenheiro)</h2>
        {d.validacao && d.validacao.status !== "pendente" ? (
          <p className="text-sm" data-testid="urb-validacao-estado">{d.validacao.status === "validado" ? "Processo validado" : "Reservas emitidas"} por {d.validacao.signatario}{d.validacao.numero_inscricao ? ` (${d.validacao.ordem || "Ordem"} n.º ${d.validacao.numero_inscricao})` : ""}{d.validacao.comentario ? ` — «${d.validacao.comentario}»` : ""}</p>
        ) : d.validacao?.status === "pendente" ? (
          <p className="text-sm break-all" data-testid="urb-validacao-estado">Pedido enviado a {d.validacao.tecnico_nome}{d.validacao.email_sent ? " por e-mail" : ""}. Ligação: <a href={d.validacao.share_url} target="_blank" rel="noreferrer" className="underline">{`${window.location.origin}${d.validacao.share_url}`}</a></p>
        ) : null}
        {(!d.validacao || d.validacao.status !== "pendente") && <div className="grid sm:grid-cols-3 gap-2">
          <Input placeholder="Nome do técnico" value={tec.tecnico_nome} onChange={(e) => setTec({ ...tec, tecnico_nome: e.target.value })} data-testid="urb-tec-nome" />
          <Input placeholder="E-mail do técnico" value={tec.tecnico_email} onChange={(e) => setTec({ ...tec, tecnico_email: e.target.value })} data-testid="urb-tec-email" />
          <Button onClick={pedirValidacao} disabled={busy === "validacao"} variant="outline" data-testid="urb-tec-submit">{busy === "validacao" ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />} Pedir revisão</Button>
        </div>}
        <p className="text-[11px] text-muted-foreground">A revisão não substitui o termo de responsabilidade do autor do projeto (art.º 10.º do RJUE), disponível em Autorização de obras.</p>
      </section>

      <div className="flex justify-between items-center gap-2">
        <p className="text-[11px] text-muted-foreground border-l-2 border-amber-400 pl-3">{verif.aviso}</p>
        <Button variant="ghost" className="text-red-600 shrink-0" onClick={remover} data-testid="urb-eliminar"><Trash2 className="h-4 w-4" /> Eliminar</Button>
      </div>
    </div>
  );
}
