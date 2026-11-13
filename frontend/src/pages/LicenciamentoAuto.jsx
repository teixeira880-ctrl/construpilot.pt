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
import ImplantacaoMapa from "@/components/licenciamento/ImplantacaoMapa";

const ETAPA_LABEL = {
  localizar: "Localizar a morada", dados_oficiais: "Ler PDM, servidões, cadastro e ortofotomapa (DGT)",
  viabilidade: "Verificar se é possível construir", terreno: "Terreno e topografia", projeto: "Implantar a casa e desenhar as plantas",
  verificacao: "Quadro de áreas, PDM, RGEU e RJUE", documentos: "Memória descritiva e peças", coerencia: "Controlo de coerência entre motores",
};
const PROC = { licenciamento: "Licença (licenciamento)", comunicacao_previa: "Comunicação prévia", isento: "Isento de controlo prévio" };
const EXEMPLO = "Quero uma autorização de construção para uma casa T3 com garagem na Rua do Monte nº 7, Padim da Graça, Braga";

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
      const { data } = await api.post("/urbanismo-auto/pedidos", { texto });
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
  const casa = useRef(null);

  const carregar = useCallback(async () => {
    const [a, b] = await Promise.all([api.get(`/urbanismo-auto/processos/${pid}`), api.get(`/urbanismo-auto/processos/${pid}/modelo3d`)]);
    setD(a.data); setModelo(b.data);
  }, [pid]);
  useEffect(() => { carregar().catch(() => setErro("Processo não encontrado.")); }, [carregar]);

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
      <Card className="p-0 overflow-hidden">
        <div className="px-4 py-3 border-b flex flex-wrap items-center justify-between gap-2">
          <div className="font-medium flex items-center gap-2"><MapPin className="h-4 w-4" />Implantação no terreno real</div>
          <span className="text-xs text-muted-foreground">Ortofotomapa oficial · arraste a casa · linhas vermelhas = afastamento em falta</span>
        </div>
        <ImplantacaoMapa pid={pid} auto={a} onAplicado={carregar} />
      </Card>

      {render && (
        <Card className="p-3"><img src={render} alt="Imagem fotorrealista da moradia" className="w-full rounded" />
          <p className="text-xs text-muted-foreground mt-2">Imagem ilustrativa gerada sobre a vista 3D exata; as medidas de referência são as das peças desenhadas.</p></Card>
      )}

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
          {(a.terreno?.poligono_latlon || []).length >= 3 && (
            <Button asChild variant="outline"><Link to="/mdt" state={{ poligono: a.terreno.poligono_latlon, local: p.terreno?.morada || "" }} data-testid="lic-auto-mdt">
              Carta de declives e linhas de água (MDT)</Link></Button>
          )}
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
