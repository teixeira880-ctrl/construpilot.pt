import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AlertTriangle, Box, CheckCircle2, Download, FileText, Image as ImageIcon, Loader2, MapPin, ShieldCheck, Sparkles, Wand2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import Casa3D from "@/components/licenciamento/Casa3D";

const ETAPA_LABEL = {
  localizar: "Localizar a morada", dados_oficiais: "Ler PDM, servidões, cadastro e ortofotomapa (DGT)",
  viabilidade: "Verificar se é possível construir", terreno: "Terreno e topografia", projeto: "Implantar a casa e desenhar as plantas",
  verificacao: "Quadro de áreas, PDM, RGEU e RJUE", documentos: "Memória descritiva e peças", coerencia: "Controlo de coerência entre motores",
  imagens: "Imagens realistas da casa (3D, antes e depois)",
};
const TIPO_IMG = { fotorrealista: "Fotorrealista", exata: "Vista 3D exata", antes: "Antes", depois: "Depois", depois_esquema: "Depois (esquema à escala)",
  implantacao: "Planta de implantação", montagem: "Montagem na sua foto" };
const VISTA_IMG = { perspetiva: "perspetiva", frente: "frente", tardoz: "jardim", aerea: "aérea", aerea_orto: "vista de cima", piscina: "piscina",
  perspetiva_entardecer: "ao entardecer", interior_sala: "sala", interior_cozinha: "cozinha", interior_suite: "suite",
  interior_wc: "casa de banho", implantacao: "a cores", foto_terreno: "terreno" };
const EXEMPLOS = [
  "Casa térrea em L com 200 m2 habitáveis, piscina e garagem exterior, terreno de 1500 m2, fachadas em granito e madeira, na Rua do Monte 7, Padim da Graça, Braga",
  "Moradia T3 de dois pisos estilo tradicional português com garagem, na Rua do Monte 7, Padim da Graça, Braga",
  "Casa alentejana térrea de 3 quartos com piscina, terreno de 1000 m2, na Rua do Monte 7, Padim da Graça, Braga",
];
const PROC = { licenciamento: "Licença (licenciamento)", comunicacao_previa: "Comunicação prévia", isento: "Isento de controlo prévio" };
const EXEMPLO = EXEMPLOS[0];

function AuthImg({ path, alt }) {
  const [url, setUrl] = useState(null);
  useEffect(() => {
    let alive = true, u = null;
    api.get(path, { responseType: "blob", timeout: 120000 }).then(r => { if (!alive) return; u = URL.createObjectURL(r.data); setUrl(u); }).catch(() => {});
    return () => { alive = false; if (u) URL.revokeObjectURL(u); };
  }, [path]);
  return url ? <img src={url} alt={alt} className="w-full aspect-[16/11] object-cover bg-white" />
    : <div className="w-full aspect-[16/11] bg-muted animate-pulse" />;
}

async function descarregar(path, nome) {
  const r = await api.get(path, { responseType: "blob", timeout: 180000 });
  const u = URL.createObjectURL(r.data);
  const a = document.createElement("a");
  a.href = u; a.download = nome; a.click();
  setTimeout(() => URL.revokeObjectURL(u), 4000);
}

function Pedido() {
  const nav = useNavigate();
  const [texto, setTexto] = useState("");
  const [job, setJob] = useState(null);
  const [erro, setErro] = useState("");
  const timer = useRef(null);

  useEffect(() => () => clearTimeout(timer.current), []);
  const seguir = useCallback(async (id) => {
    try {
      const { data } = await api.get(`/urbanismo-auto/pedidos/${id}`);
      setJob(data);
      if (data.estado === "concluido") {
        const r = data.resultado || {};
        if (r.ok && r.processo_id) nav(`/licenciamento-automatico/${r.processo_id}`);
        return;
      }
      if (data.estado === "erro") { setErro(data.erro || "Ocorreu um erro."); return; }
      timer.current = setTimeout(() => seguir(id), 1500);
    } catch (e) { setErro("Não foi possível acompanhar o pedido."); }
  }, [nav]);

  const enviar = async () => {
    setErro(""); setJob(null);
    try {
      const { data } = await api.post("/urbanismo-auto/dossier-completo", { texto });
      setJob({ estado: "a_correr", etapas: [], etapas_previstas: data.etapas_previstas });
      seguir(data.job_id);
    } catch (e) { setErro(e?.response?.data?.detail || "Não foi possível iniciar o pedido."); }
  };
  const feitas = new Set((job?.etapas || []).map(e => e.etapa));
  const r = job?.resultado;
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6" data-testid="lic-auto-pedido">
      <div>
        <h1 className="text-2xl sm:text-3xl font-semibold">Autorização de construção automática</h1>
        <p className="text-muted-foreground mt-2">Escreva o que quer e a morada. O ConstruPilot lê os dados oficiais do terreno, desenha a casa,
          verifica as regras e prepara o processo completo — com tudo o que assumiu explicado em linguagem simples.</p>
      </div>
      <Card className="p-4 space-y-3">
        <Textarea rows={3} value={texto} onChange={e => setTexto(e.target.value)} placeholder={EXEMPLO} data-testid="lic-auto-texto" />
        <div className="flex flex-wrap gap-2">
          <Button onClick={enviar} disabled={!texto.trim() || job?.estado === "a_correr"} data-testid="lic-auto-enviar">
            {job?.estado === "a_correr" ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Wand2 className="h-4 w-4 mr-2" />}Fazer tudo automaticamente
          </Button>
          <Button variant="outline" onClick={() => setTexto(EXEMPLO)}>Usar o exemplo</Button>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          {EXEMPLOS.slice(1).map(x => <button key={x} type="button" className="rounded-full border px-3 py-1 hover:bg-accent text-left" onClick={() => setTexto(x)}>{x.split(",")[0]}</button>)}
        </div>
        <p className="text-xs text-muted-foreground">Pode escrever como fala: forma da casa (em L…), área habitável, área do terreno, piscina, garagem, estilo
          (contemporâneo, tradicional, minhoto, alentejano…), materiais. O que faltar, decidimos nós e explicamos no fim.</p>
      </Card>
      {job && (
        <Card className="p-4 space-y-2" data-testid="lic-auto-etapas">
          {(job.etapas_previstas || []).map(k => {
            const e = (job.etapas || []).find(x => x.etapa === k);
            return (
              <div key={k} className="flex items-start gap-2 text-sm">
                {e ? <CheckCircle2 className="h-4 w-4 mt-0.5 text-emerald-600" /> : job.estado === "a_correr" && feitas.size === (job.etapas_previstas || []).indexOf(k)
                  ? <Loader2 className="h-4 w-4 mt-0.5 animate-spin" /> : <span className="h-4 w-4 mt-0.5 rounded-full border" />}
                <div><div className="font-medium">{ETAPA_LABEL[k] || k}</div>{e?.detalhe && <div className="text-muted-foreground text-xs">{e.detalhe}</div>}</div>
              </div>
            );
          })}
        </Card>
      )}
      {r && !r.ok && (
        <Card className="p-4 border-amber-300 bg-amber-50 space-y-2" data-testid="lic-auto-bloqueio">
          <div className="flex items-center gap-2 font-medium"><AlertTriangle className="h-4 w-4" />Não foi possível avançar</div>
          {r.resposta && <p className="text-sm">{r.resposta}</p>}
          {r.motivo && <p className="text-sm">{r.motivo}</p>}
          {(r.perguntas || []).map((q, i) => <p key={i} className="text-sm">• {q}</p>)}
        </Card>
      )}
      {erro && <p className="text-sm text-red-600">{erro}</p>}
    </div>
  );
}

function Processo({ pid }) {
  const [d, setD] = useState(null);
  const [modelo, setModelo] = useState(null);
  const [render, setRender] = useState(null);
  const [aRender, setARender] = useState(false);
  const [resp, setResp] = useState({ area_terreno_m2: "", nome: "", nif: "" });
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState("");
  const [mudanca, setMudanca] = useState("");
  const [estilos, setEstilos] = useState([]);
  const [imgs, setImgs] = useState({ imagens: [], job: null, desatualizadas: false });
  const [zoom, setZoom] = useState(null);
  const casa = useRef(null);
  const imgTimer = useRef(null);

  const carregar = useCallback(async () => {
    const [a, b] = await Promise.all([api.get(`/urbanismo-auto/processos/${pid}`), api.get(`/urbanismo-auto/processos/${pid}/modelo3d`)]);
    setD(a.data); setModelo(b.data);
  }, [pid]);
  useEffect(() => { carregar().catch(() => setErro("Processo não encontrado.")); }, [carregar]);
  const carregarImgs = useCallback(async () => {
    const { data } = await api.get(`/urbanismo-auto/processos/${pid}/imagens`);
    setImgs(data);
    if (data.job?.estado === "a_correr") imgTimer.current = setTimeout(() => carregarImgs().catch(() => {}), 3000);
  }, [pid]);
  useEffect(() => {
    carregarImgs().catch(() => {});
    api.get("/urbanismo-auto/estilos").then(r => setEstilos(r.data.estilos || [])).catch(() => {});
    return () => clearTimeout(imgTimer.current);
  }, [carregarImgs]);
  const gerarImgs = async () => {
    setErro("");
    try { await api.post(`/urbanismo-auto/processos/${pid}/imagens`, {}); await carregarImgs(); }
    catch (e) { setErro(e?.response?.data?.detail || "Não foi possível pedir as imagens."); }
  };
  const fotoRef = useRef(null);
  const enviarFoto = async (f) => {
    if (!f) return;
    setErro("");
    const fd = new FormData();
    fd.append("ficheiro", f);
    try { await api.post(`/urbanismo-auto/processos/${pid}/foto-terreno`, fd); await gerarImgs(); }
    catch (e) { setErro(e?.response?.data?.detail || "Não foi possível enviar a fotografia."); }
  };
  const aprovar = async (i, aprovada) => {
    try { await api.post(`/urbanismo-auto/processos/${pid}/imagens/${i.id}/aprovar`, { aprovada }); await carregarImgs(); }
    catch (e) { setErro(e?.response?.data?.detail || "Não foi possível guardar a aprovação."); }
  };
  const mudarProjeto = async (body) => {
    setOcupado(true); setErro("");
    try {
      const { data } = await api.patch(`/urbanismo-auto/processos/${pid}/projeto`, body);
      if (!data.ok) setErro(data.motivo || data.resposta || (data.perguntas || []).join(" ") || "Não foi possível aplicar a mudança.");
      setMudanca(""); setRender(null);
      await carregar(); await carregarImgs();
    } catch (e) { setErro(e?.response?.data?.detail || "Erro ao aplicar a mudança."); }
    setOcupado(false);
  };

  const material = async (campo, valor) => {
    await api.patch(`/urbanismo-auto/processos/${pid}/materiais`, { [campo]: valor });
    setRender(null); await carregar();
  };
  const refazer = async () => {
    setOcupado(true); setErro("");
    try {
      const body = {};
      if (resp.area_terreno_m2) body.area_terreno_m2 = Number(resp.area_terreno_m2);
      if (resp.nome || resp.nif) body.requerente = { nome: resp.nome, nif: resp.nif };
      const { data } = await api.post(`/urbanismo-auto/processos/${pid}/refazer`, body);
      if (!data.ok) setErro(data.motivo || (data.bloqueios || []).join(" ") || "Não foi possível recalcular.");
      await carregar();
    } catch (e) { setErro(e?.response?.data?.detail || "Erro ao recalcular."); }
    setOcupado(false);
  };
  const fotorrealista = async () => {
    const img = casa.current?.snapshot();
    if (!img) return;
    setARender(true); setErro("");
    try {
      const { data } = await api.post(`/urbanismo-auto/processos/${pid}/render`, { imagem_b64: img });
      setRender(`data:${data.mime};base64,${data.imagem_b64}`);
    } catch (e) { setErro(e?.response?.data?.detail || "A imagem fotorrealista não está disponível agora."); }
    setARender(false);
  };

  if (erro && !d) return <div className="p-8 text-center">{erro}</div>;
  if (!d) return <div className="p-8 flex justify-center"><Loader2 className="h-6 w-6 animate-spin" /></div>;
  const p = d.processo, a = p.auto || {}, v = d.verificacao, q = v.quadro || {}, c = d.coerencia;
  const cat = d.catalogo_materiais || {};
  const mat = a.materiais || {};
  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6" data-testid="lic-auto-processo">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{p.title}</h1>
          <p className="text-muted-foreground text-sm flex items-center gap-1"><MapPin className="h-4 w-4" />{p.terreno?.morada}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge className="text-sm">{PROC[v.rjue?.procedimento] || v.rjue?.procedimento}</Badge>
          <Badge variant={c.ok ? "default" : "destructive"} className="text-sm" data-testid="lic-auto-coerencia">
            <ShieldCheck className="h-3.5 w-3.5 mr-1" />Coerência {c.aprovados}/{c.total}
          </Badge>
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <Card className="p-0 lg:col-span-2 overflow-hidden">
          {modelo && <Casa3D ref={casa} modelo={modelo} altura={460} />}
          <div className="p-3 flex flex-wrap gap-2 items-center border-t">
            {["perspetiva", "frente", "tardoz", "aerea"].map(n => <Button key={n} size="sm" variant="outline" onClick={() => casa.current?.vista(n)}>{n === "aerea" ? "Aérea" : n[0].toUpperCase() + n.slice(1)}</Button>)}
            <Button size="sm" onClick={fotorrealista} disabled={aRender} data-testid="lic-auto-render">
              {aRender ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <ImageIcon className="h-4 w-4 mr-1" />}Imagem fotorrealista
            </Button>
          </div>
        </Card>
        <Card className="p-4 space-y-3">
          <div className="font-medium flex items-center gap-2"><Box className="h-4 w-4" />Materiais</div>
          {[["fachada", "Fachadas"], ["cobertura", "Cobertura"], ["caixilharia", "Caixilharia"]].map(([k, lbl]) => (
            <label key={k} className="block text-sm">{lbl}
              <select className="mt-1 w-full border rounded h-9 px-2 bg-background" value={mat[k] || ""} onChange={e => material(k, e.target.value)} data-testid={`lic-auto-mat-${k}`}>
                {Object.entries(cat[k] || {}).map(([val, txt]) => <option key={val} value={val}>{txt}</option>)}
              </select>
            </label>
          ))}
          <div className="text-sm space-y-1 pt-2 border-t">
            <div>Tipologia <b>{a.programa?.tipologia}</b> · {q.n_pisos} piso(s)</div>
            <div>Construção <b>{q.area_construcao_m2} m²</b> · implantação {q.area_implantacao_m2} m²</div>
            <div>Terreno {q.area_terreno_m2} m² · ocupação {q.indice_ocupacao_pct} %</div>
            <div>Fachada {q.altura_fachada_m} m · total {q.altura_total_m} m</div>
          </div>
        </Card>
      </div>
      {render && (
        <Card className="p-3"><img src={render} alt="Imagem fotorrealista da moradia" className="w-full rounded" />
          <p className="text-xs text-muted-foreground mt-2">Imagem ilustrativa gerada sobre a vista 3D exata; as medidas de referência são as das peças desenhadas.</p></Card>
      )}

      <Card className="p-4 space-y-3" data-testid="lic-auto-imagens">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="font-medium flex items-center gap-2"><ImageIcon className="h-4 w-4" />Imagens realistas</div>
          <div className="flex flex-wrap gap-2">
            <input ref={fotoRef} type="file" accept="image/*" className="hidden" data-testid="lic-auto-foto-input"
              onChange={e => { enviarFoto(e.target.files?.[0]); e.target.value = ""; }} />
            <Button size="sm" variant="outline" onClick={() => fotoRef.current?.click()} disabled={imgs.job?.estado === "a_correr"}
              data-testid="lic-auto-foto-terreno">Enviar foto do terreno</Button>
            <Button size="sm" onClick={gerarImgs} disabled={imgs.job?.estado === "a_correr"} data-testid="lic-auto-gerar-imagens">
              {imgs.job?.estado === "a_correr" ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Wand2 className="h-4 w-4 mr-1" />}
              {imgs.imagens.length ? "Atualizar imagens" : "Criar imagens realistas"}
            </Button>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">Exteriores de dia e ao entardecer, piscina, vista aérea, interiores (sala, cozinha, suite,
          casa de banho) e planta a cores. Com uma fotografia do terreno vazio (telemóvel ou drone), criamos também a montagem da casa nessa foto.</p>
        {imgs.job?.estado === "a_correr" && <p className="text-sm text-muted-foreground">A criar as imagens (2 a 5 minutos)…</p>}
        {imgs.job?.estado === "erro" && <p className="text-sm text-red-600">{imgs.job.erro}</p>}
        {imgs.desatualizadas && imgs.imagens.length > 0 && <p className="text-sm text-amber-700">O projeto mudou depois destas imagens: atualize-as para as juntar ao processo.</p>}
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {imgs.imagens.filter(i => i.tipo !== "exata" || !imgs.imagens.some(j => j.vista === i.vista && j.tipo === "fotorrealista" && j.verificada)).map(i => (
            <div key={i.id} className="border rounded overflow-hidden hover:shadow" data-testid={`lic-auto-img-${i.tipo}`}>
              <button type="button" onClick={() => setZoom(i)} className="block w-full text-left">
                <AuthImg path={`/urbanismo-auto/processos/${pid}/imagens/${i.id}.jpg`} alt={`${TIPO_IMG[i.tipo]} — ${VISTA_IMG[i.vista] || i.vista}`} />
              </button>
              <div className="p-2 text-xs flex items-center justify-between gap-2">
                <span>{TIPO_IMG[i.tipo] || i.tipo} · {VISTA_IMG[i.vista] || i.vista}</span>
                {i.tipo === "fotorrealista" && (i.verificada
                  ? <span className="text-emerald-700">✓ geometria verificada</span>
                  : <span className="text-amber-700">⚠ comparar com a vista exata</span>)}
                {i.tipo === "montagem" && (i.aprovada
                  ? <button type="button" className="text-emerald-700 underline" onClick={() => aprovar(i, false)}>✓ no dossier (retirar)</button>
                  : <button type="button" className="text-blue-700 underline" onClick={() => aprovar(i, true)}
                      data-testid="lic-auto-aprovar-montagem">Aprovar para o dossier</button>)}
              </div>
            </div>
          ))}
        </div>
        {zoom && (
          <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4" onClick={() => setZoom(null)} role="dialog">
            <div className="max-w-6xl w-full"><AuthImg path={`/urbanismo-auto/processos/${pid}/imagens/${zoom.id}.jpg`} alt="" />
              <p className="text-xs text-white/80 mt-2">{zoom.nota}</p></div>
          </div>
        )}
        <p className="text-xs text-muted-foreground">Imagens ilustrativas feitas sobre a geometria exata do projeto e verificadas automaticamente; entram nas peças
          desenhadas (PDF) e no processo (ZIP). As medidas de referência são as dos desenhos.</p>
      </Card>

      <Card className="p-4 space-y-3" data-testid="lic-auto-mudar">
        <div className="font-medium flex items-center gap-2"><Sparkles className="h-4 w-4" />Mudar o projeto</div>
        <div className="flex flex-wrap gap-2">
          {estilos.map(e => (
            <button key={e.id} type="button" title={e.descricao} disabled={ocupado} onClick={() => mudarProjeto({ estilo: e.id })}
              className={`rounded-full border px-3 py-1 text-xs ${a.estilo?.id === e.id ? "bg-primary text-primary-foreground" : "hover:bg-accent"}`}>{e.nome}</button>
          ))}
        </div>
        <div className="flex flex-col sm:flex-row gap-2">
          <Input placeholder="Diga o que quer mudar: «em L», «mais um quarto», «sem piscina», «2 pisos», «fachada em xisto»…" value={mudanca}
            onChange={e => setMudanca(e.target.value)} data-testid="lic-auto-mudanca" />
          <Button onClick={() => mudarProjeto({ texto: mudanca })} disabled={ocupado || !mudanca.trim()} data-testid="lic-auto-aplicar-mudanca">
            {ocupado && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}Aplicar e recalcular</Button>
        </div>
        <p className="text-xs text-muted-foreground">Tudo é recalculado e verificado de novo (implantação, plantas, quadro, memória). Estilo atual: <b>{a.estilo?.nome || "—"}</b>
          {a.forma === "l" ? " · casa em L" : ""}{a.piscina ? ` · piscina ${a.piscina.l_m}×${a.piscina.w_m} m` : ""}{a.garagem_tipo === "exterior" ? " · garagem independente" : ""}</p>
      </Card>

      <div className="grid md:grid-cols-2 gap-4">
        <Card className="p-4 space-y-2">
          <div className="font-medium flex items-center gap-2"><Sparkles className="h-4 w-4" />O que decidi</div>
          {(a.implantacao?.decisoes || []).map((x, i) => <p key={i} className="text-sm">• {x}</p>)}
        </Card>
        <Card className="p-4 space-y-2 border-amber-200">
          <div className="font-medium flex items-center gap-2"><AlertTriangle className="h-4 w-4 text-amber-600" />O que assumi (a confirmar)</div>
          {(a.pressupostos || []).map((x, i) => <p key={i} className="text-sm">• {x}</p>)}
          {(a.avisos || []).map((x, i) => <p key={`w${i}`} className="text-sm text-amber-800">• {x}</p>)}
        </Card>
      </div>
      {(a.a_completar || []).length > 0 && (
        <Card className="p-4 space-y-2" data-testid="lic-auto-a-completar">
          <div className="font-medium">Para completar quando quiser (não impede nada)</div>
          {a.a_completar.map((x, i) => <p key={i} className="text-sm">• {x}</p>)}
        </Card>
      )}

      <Card className="p-4 space-y-3">
        <div className="font-medium">Afinar com os seus dados (opcional)</div>
        <div className="grid sm:grid-cols-3 gap-2">
          <Input placeholder="Área da caderneta (m²)" value={resp.area_terreno_m2} onChange={e => setResp({ ...resp, area_terreno_m2: e.target.value })} data-testid="lic-auto-area" />
          <Input placeholder="Nome do requerente" value={resp.nome} onChange={e => setResp({ ...resp, nome: e.target.value })} />
          <Input placeholder="NIF" value={resp.nif} onChange={e => setResp({ ...resp, nif: e.target.value })} />
        </div>
        <Button onClick={refazer} disabled={ocupado} data-testid="lic-auto-refazer">{ocupado && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}Recalcular tudo</Button>
        {erro && <p className="text-sm text-red-600">{erro}</p>}
      </Card>

      <Card className="p-4 space-y-3">
        <div className="font-medium flex items-center gap-2"><FileText className="h-4 w-4" />Peças do processo</div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {(d.desenhos || []).map(x => (
            <button type="button" key={x.n} onClick={() => descarregar(`/urbanismo-auto/processos/${pid}/desenhos/${x.n}.png`, `${x.code.toLowerCase()}_${x.n}.png`)}
              className="block text-left border rounded overflow-hidden hover:shadow">
              <AuthImg path={`/urbanismo-auto/processos/${pid}/desenhos/${x.n}.png`} alt={x.title} />
              <div className="p-2 text-xs">{x.title}</div>
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => descarregar(`/urbanismo-auto/processos/${pid}/pecas-desenhadas.pdf`, "pecas-desenhadas.pdf")}>
            <Download className="h-4 w-4 mr-1" />Peças desenhadas (PDF)</Button>
          <Button disabled={!c.ok} onClick={() => descarregar(`/urbanismo-auto/processos/${pid}/export.zip`, "processo-licenciamento.zip").catch(() => setErro("Não foi possível exportar."))} data-testid="lic-auto-zip">
            <Download className="h-4 w-4 mr-1" />Processo completo (ZIP)</Button>
          <Button asChild variant="outline"><Link to="/particulares/autorizacao-obras">Pedir assinatura de arquiteto / engenheiro</Link></Button>
        </div>
        <p className="text-xs text-muted-foreground">O levantamento topográfico por topógrafo, os projetos de especialidades e os termos de responsabilidade
          dos técnicos (art.º 10.º do RJUE) são obrigatórios antes de entregar na câmara. {v.aviso}</p>
      </Card>

      <Card className="p-4">
        <details>
          <summary className="cursor-pointer font-medium">Controlo de coerência ({c.aprovados}/{c.total}) e fontes</summary>
          <div className="mt-3 space-y-1 text-sm">
            {(c.checks || []).map(k => <div key={k.codigo} className={k.ok ? "" : "text-red-600"}>{k.ok ? "✓" : "✗"} {k.descricao}: {String(k.obtido)}</div>)}
            <div className="pt-2 text-muted-foreground">Fontes: {(a.fontes || []).map(f => f.fonte).join(" · ")}</div>
          </div>
        </details>
      </Card>
    </div>
  );
}

export default function LicenciamentoAuto() {
  const { id } = useParams();
  return id ? <Processo pid={id} /> : <Pedido />;
}
