import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, ArrowRight, CheckCircle2, Download, FileText, HardHat, Hammer, Package, Scale, ShieldAlert, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { SEO } from "@/components/SEO";

const API = process.env.REACT_APP_BACKEND_URL;

const TIPOS = [
  { v: "anexo", label: "Anexo / telheiro / arrumos", icon: HardHat, help: "Edificação contígua ou não ao edifício principal (anexos, barracos)." },
  { v: "muro", label: "Muro ou vedação", icon: Scale, help: "Muros de vedação ou de suporte de terras." },
  { v: "interiores", label: "Obras só no interior", icon: Hammer, help: "Alteração interior sem mexer na fachada, telhado ou alterar o uso." },
  { v: "piscina", label: "Piscina", icon: Sparkles, help: "Piscina associada a edificação principal." },
  { v: "ampliacao", label: "Ampliação de edifício existente", icon: ArrowRight, help: "Aumentar área, piso ou altura do edifício existente." },
  { v: "moradia_nova", label: "Construção nova (moradia)", icon: FileText, help: "Nova moradia unifamiliar ou edifício novo." },
];

const PROCEDIMENTO_LABEL = {
  isento: { label: "Isento de controlo prévio", tone: "bg-emerald-100 text-emerald-900 border-emerald-200" },
  comunicacao_previa: { label: "Comunicação prévia", tone: "bg-amber-100 text-amber-900 border-amber-200" },
  licenciamento: { label: "Licenciamento", tone: "bg-rose-100 text-rose-900 border-rose-200" },
};

const TECNICO_LABEL = {
  arquiteto: "Arquiteto(a)",
  engenheiro_estruturas: "Engenheiro(a) de estruturas",
  engenheiro_civil: "Engenheiro(a) civil",
  engenheiro_eletrotecnico: "Engenheiro(a) eletrotécnico(a)",
  engenheiro_civil_ou_eletrotecnico: "Engenheiro(a) civil ou eletrotécnico(a)",
  coordenador_projeto: "Coordenador(a) de projeto",
};

const INITIAL = {
  tipo_obra: null,
  subtipo_muro: "vedacao",
  area_implantacao_m2: 0,
  area_construcao_total_m2: 0,
  area_construcao_criada_m2: 0,
  altura_m: 0,
  indice_implantacao: null,
  afastamento_min_m: null,
  concelho: "",
  freguesia: "",
  confina_via_publica: false,
  zona_protegida: false,
  imovel_classificado: false,
  tem_edificacao_principal: true,
  altera_fachada: false,
  altera_uso: false,
  altera_cobertura: false,
  tem_pdm_com_parametros: false,
  tem_loteamento_pip: false,
  zona_urbana_consolidada: false,
  pdm_altura_max_m: null,
  pdm_indice_implantacao: null,
  pdm_afastamento_min_m: null,
};

const StepHeader = ({ step, total, title }) => (
  <div className="flex items-center justify-between mb-4">
    <span className="text-xs font-semibold uppercase tracking-widest text-muted-foreground" data-testid="autorizacao-step-counter">
      Passo {step} / {total}
    </span>
    <h1 className="sr-only">{title}</h1>
    <div className="h-1.5 flex-1 ml-4 bg-muted rounded overflow-hidden">
      <div className="h-full bg-primary transition-all" style={{ width: `${Math.round((step / total) * 100)}%` }} />
    </div>
  </div>
);

export default function AutorizacaoObras() {
  const [state, setState] = useState(INITIAL);
  const [step, setStep] = useState(0);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const TOTAL_STEPS = 7;

  useEffect(() => { window.scrollTo({ top: 0, behavior: "smooth" }); }, [step, result]);

  const canNext = useMemo(() => {
    if (step === 0) return !!state.tipo_obra;
    return true;
  }, [step, state.tipo_obra]);

  const set = (k, v) => setState((s) => ({ ...s, [k]: v }));

  const submit = async () => {
    setLoading(true); setError(null);
    try {
      const r = await fetch(`${API}/api/particulares/autorizacao/diagnostico`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(state),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setResult(data);
    } catch (e) {
      setError(e.message || "Erro ao obter diagnóstico");
    } finally {
      setLoading(false);
    }
  };

  const reset = () => { setState(INITIAL); setStep(0); setResult(null); setError(null); };

  if (result) {
    const procMeta = PROCEDIMENTO_LABEL[result.procedimento] || PROCEDIMENTO_LABEL.licenciamento;
    return (
      <>
        <SEO title="Diagnóstico de autorização de obras — ConstruPilot" />
        <div className="max-w-3xl mx-auto px-4 sm:px-6 py-6 pb-24" data-testid="autorizacao-resultado">
          <div className="flex items-center justify-between mb-6">
            <Link to="/particulares" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground" data-testid="autorizacao-voltar-landing">
              <ArrowLeft size={16} /> Voltar
            </Link>
            <Button variant="outline" size="sm" onClick={reset} data-testid="autorizacao-recomecar">Novo diagnóstico</Button>
          </div>

          <Card className="p-5 sm:p-7 mb-6 border">
            <Badge className={`inline-block mb-3 border ${procMeta.tone}`} data-testid="autorizacao-procedimento-badge">
              {procMeta.label}
            </Badge>
            <h2 className="text-xl sm:text-2xl font-semibold mb-2" data-testid="autorizacao-regra-titulo">
              {result.titulo_regra}
            </h2>
            <p className="text-sm text-foreground/80 leading-relaxed" data-testid="autorizacao-fundamento">
              {result.fundamento_legal}
            </p>
          </Card>

          {result.tecnicos_obrigatorios?.length > 0 && (
            <Card className="p-5 mb-4" data-testid="autorizacao-tecnicos">
              <h3 className="font-semibold mb-3 flex items-center gap-2"><HardHat size={18} /> Técnicos obrigatórios</h3>
              <ul className="space-y-1.5 text-sm">
                {result.tecnicos_obrigatorios.map((t) => (
                  <li key={t} className="flex items-start gap-2">
                    <CheckCircle2 size={16} className="mt-0.5 text-emerald-600 flex-shrink-0" />
                    <span>{TECNICO_LABEL[t] || t}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {result.pecas_necessarias?.length > 0 && (
            <Card className="p-5 mb-4" data-testid="autorizacao-pecas">
              <h3 className="font-semibold mb-3 flex items-center gap-2"><FileText size={18} /> Peças necessárias</h3>
              <ul className="space-y-1.5 text-sm">
                {result.pecas_necessarias.map((p, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <CheckCircle2 size={16} className="mt-0.5 text-emerald-600 flex-shrink-0" />
                    <span>{p}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {result.avisos?.length > 0 && (
            <Card className="p-5 mb-4 border-amber-200 bg-amber-50/40" data-testid="autorizacao-avisos">
              <h3 className="font-semibold mb-3 flex items-center gap-2 text-amber-900"><ShieldAlert size={18} /> Avisos</h3>
              <ul className="space-y-1.5 text-sm text-amber-950/90">
                {result.avisos.map((a, i) => <li key={i}>• {a}</li>)}
              </ul>
            </Card>
          )}

          {result.referencias_legais?.length > 0 && (
            <Card className="p-5 mb-4" data-testid="autorizacao-referencias">
              <h3 className="font-semibold mb-3">Referências legais</h3>
              <ul className="space-y-2 text-sm">
                {result.referencias_legais.map((ref, i) => (
                  <li key={i} className="leading-relaxed">
                    <a href={ref.url} target="_blank" rel="noopener noreferrer" className="font-medium text-primary underline">
                      Artigo {ref.artigo} do RJUE
                    </a>
                    <span className="text-foreground/70"> — {ref.descricao}</span>
                  </li>
                ))}
                {result.lei_base?.versao_consolidada_url && (
                  <li className="pt-2 text-xs text-muted-foreground">
                    Versão consolidada: <a href={result.lei_base.versao_consolidada_url} target="_blank" rel="noopener noreferrer" className="underline">{result.lei_base.codigo} — {result.lei_base.titulo}</a>
                  </li>
                )}
              </ul>
            </Card>
          )}

          <p className="text-xs text-muted-foreground leading-relaxed mt-6" data-testid="autorizacao-aviso-legal">
            Esta ferramenta é um apoio à preparação do processo de autorização de obras. A responsabilidade legal
            do processo é do requerente e dos técnicos subscritores. Os prazos indicados são meramente indicativos —
            confirme com a câmara municipal do seu concelho. A submissão oficial é feita exclusivamente através da
            PEPU ou do balcão único eletrónico do município.
          </p>
          <p className="text-xs mt-2">
            <a href={`${API}/api/particulares/autorizacao/guia-pepu.pdf`} target="_blank" rel="noopener noreferrer"
               className="underline text-primary" data-testid="autorizacao-guia-pepu">
              Descarregar o guia de submissão PEPU (PDF)
            </a>
          </p>

          <DossierBlock respostas={state} diagnostico={result} />
        </div>
      </>
    );
  }

  return (
    <>
      <SEO title="Autorização de obras — diagnóstico guiado — ConstruPilot" />
      <div className="max-w-xl mx-auto px-4 sm:px-6 py-6 pb-24" data-testid="autorizacao-wizard">
        <Link to="/particulares" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-4" data-testid="autorizacao-voltar">
          <ArrowLeft size={16} /> Voltar
        </Link>
        <StepHeader step={step + 1} total={TOTAL_STEPS} title="Diagnóstico de autorização de obras" />

        {step === 0 && (
          <section data-testid="autorizacao-step-tipo">
            <h2 className="text-xl sm:text-2xl font-semibold mb-1">Que tipo de obra quer fazer?</h2>
            <p className="text-sm text-muted-foreground mb-5">Escolha a opção que melhor descreve a sua intenção.</p>
            <div className="grid gap-2">
              {TIPOS.map((t) => {
                const Icon = t.icon;
                const active = state.tipo_obra === t.v;
                return (
                  <button key={t.v} type="button" onClick={() => set("tipo_obra", t.v)}
                          data-testid={`autorizacao-tipo-${t.v}`}
                          className={`text-left p-4 rounded-lg border transition flex items-start gap-3 ${active ? "border-primary bg-primary/5" : "border-border hover:border-foreground/30"}`}>
                    <Icon size={22} className={active ? "text-primary" : "text-muted-foreground"} />
                    <div>
                      <div className="font-medium">{t.label}</div>
                      <div className="text-xs text-muted-foreground mt-0.5">{t.help}</div>
                    </div>
                  </button>
                );
              })}
            </div>
          </section>
        )}

        {step === 1 && (
          <section data-testid="autorizacao-step-local">
            <h2 className="text-xl sm:text-2xl font-semibold mb-1">Localização</h2>
            <p className="text-sm text-muted-foreground mb-5">Dados básicos sobre o local da obra.</p>
            <div className="space-y-3">
              <div>
                <Label htmlFor="concelho">Concelho</Label>
                <Input id="concelho" value={state.concelho} onChange={(e) => set("concelho", e.target.value)} placeholder="Ex.: Setúbal" data-testid="autorizacao-concelho" />
              </div>
              <div>
                <Label htmlFor="freguesia">Freguesia</Label>
                <Input id="freguesia" value={state.freguesia} onChange={(e) => set("freguesia", e.target.value)} placeholder="Ex.: São Sebastião" data-testid="autorizacao-freguesia" />
              </div>
              <label className="flex items-start gap-2 cursor-pointer p-3 rounded border border-border hover:border-foreground/30 transition">
                <Checkbox checked={state.imovel_classificado} onCheckedChange={(v) => set("imovel_classificado", !!v)} data-testid="autorizacao-classificado" />
                <span className="text-sm leading-relaxed"><strong>Imóvel classificado</strong> (ou em vias de classificação) de interesse nacional, público ou municipal.</span>
              </label>
              <label className="flex items-start gap-2 cursor-pointer p-3 rounded border border-border hover:border-foreground/30 transition">
                <Checkbox checked={state.zona_protegida} onCheckedChange={(v) => set("zona_protegida", !!v)} data-testid="autorizacao-zonaprotegida" />
                <span className="text-sm leading-relaxed"><strong>Zona de proteção</strong> de imóvel classificado, ARU, conjunto ou sítio classificado.</span>
              </label>
            </div>
          </section>
        )}

        {step === 2 && (
          <section data-testid="autorizacao-step-dimensoes">
            <h2 className="text-xl sm:text-2xl font-semibold mb-1">Dimensões</h2>
            <p className="text-sm text-muted-foreground mb-5">Preencha o que for aplicável à sua obra.</p>
            <div className="space-y-3">
              <div>
                <Label htmlFor="altura">Altura prevista (m)</Label>
                <Input id="altura" type="number" inputMode="decimal" step="0.1" min="0" value={state.altura_m || ""}
                       onChange={(e) => set("altura_m", parseFloat(e.target.value) || 0)}
                       data-testid="autorizacao-altura" />
              </div>
              <div>
                <Label htmlFor="area-imp">Área de implantação (m²)</Label>
                <Input id="area-imp" type="number" inputMode="decimal" step="0.1" min="0" value={state.area_implantacao_m2 || ""}
                       onChange={(e) => set("area_implantacao_m2", parseFloat(e.target.value) || 0)}
                       data-testid="autorizacao-area-imp" />
              </div>
              {["ampliacao", "moradia_nova", "piscina"].includes(state.tipo_obra) && (
                <div>
                  <Label htmlFor="area-ct">Área de construção {state.tipo_obra === "ampliacao" ? "criada" : "total"} (m²)</Label>
                  <Input id="area-ct" type="number" inputMode="decimal" step="0.1" min="0"
                         value={(state.tipo_obra === "ampliacao" ? state.area_construcao_criada_m2 : state.area_construcao_total_m2) || ""}
                         onChange={(e) => set(state.tipo_obra === "ampliacao" ? "area_construcao_criada_m2" : "area_construcao_total_m2", parseFloat(e.target.value) || 0)}
                         data-testid="autorizacao-area-ct" />
                </div>
              )}
              {state.tipo_obra === "piscina" && (
                <div>
                  <Label htmlFor="area-ed">Área da edificação principal já existente (m²)</Label>
                  <Input id="area-ed" type="number" inputMode="decimal" step="0.1" min="0" value={state.area_construcao_total_m2 || ""}
                         onChange={(e) => set("area_construcao_total_m2", parseFloat(e.target.value) || 0)}
                         data-testid="autorizacao-area-principal" />
                </div>
              )}
            </div>
          </section>
        )}

        {step === 3 && (
          <section data-testid="autorizacao-step-contexto">
            <h2 className="text-xl sm:text-2xl font-semibold mb-1">Contexto da construção</h2>
            <p className="text-sm text-muted-foreground mb-5">Características que condicionam o enquadramento legal.</p>
            <div className="space-y-3">
              <label className="flex items-start gap-2 cursor-pointer p-3 rounded border border-border">
                <Checkbox checked={state.confina_via_publica} onCheckedChange={(v) => set("confina_via_publica", !!v)} data-testid="autorizacao-via-publica" />
                <span className="text-sm">A obra confina com a <strong>via pública</strong>.</span>
              </label>
              {state.tipo_obra === "muro" && (
                <div>
                  <Label className="text-sm mb-1 block">Tipo de muro</Label>
                  <div className="flex gap-2">
                    {["vedacao", "suporte"].map((v) => (
                      <button key={v} type="button" onClick={() => set("subtipo_muro", v)}
                              data-testid={`autorizacao-submuro-${v}`}
                              className={`flex-1 py-2 rounded border text-sm ${state.subtipo_muro === v ? "border-primary bg-primary/5" : "border-border"}`}>
                        {v === "vedacao" ? "Vedação" : "Suporte de terras"}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {state.tipo_obra === "interiores" && (
                <>
                  <label className="flex items-start gap-2 cursor-pointer p-3 rounded border border-border">
                    <Checkbox checked={state.altera_fachada} onCheckedChange={(v) => set("altera_fachada", !!v)} data-testid="autorizacao-fachada" />
                    <span className="text-sm">A obra altera a <strong>fachada</strong> (vãos, cores, materiais, varandas).</span>
                  </label>
                  <label className="flex items-start gap-2 cursor-pointer p-3 rounded border border-border">
                    <Checkbox checked={state.altera_cobertura} onCheckedChange={(v) => set("altera_cobertura", !!v)} data-testid="autorizacao-cobertura" />
                    <span className="text-sm">A obra altera o <strong>telhado ou cobertura</strong>.</span>
                  </label>
                  <label className="flex items-start gap-2 cursor-pointer p-3 rounded border border-border">
                    <Checkbox checked={state.altera_uso} onCheckedChange={(v) => set("altera_uso", !!v)} data-testid="autorizacao-uso" />
                    <span className="text-sm">A obra implica <strong>alteração de uso</strong> (ex.: comércio → habitação).</span>
                  </label>
                </>
              )}
              {state.tipo_obra === "piscina" && (
                <label className="flex items-start gap-2 cursor-pointer p-3 rounded border border-border">
                  <Checkbox checked={state.tem_edificacao_principal} onCheckedChange={(v) => set("tem_edificacao_principal", !!v)} data-testid="autorizacao-principal" />
                  <span className="text-sm">Já existe uma <strong>edificação principal</strong> legalizada no terreno.</span>
                </label>
              )}
            </div>
          </section>
        )}

        {step === 4 && (
          <section data-testid="autorizacao-step-pdm-enquadramento">
            <h2 className="text-xl sm:text-2xl font-semibold mb-1">Enquadramento municipal</h2>
            <p className="text-sm text-muted-foreground mb-5">Se não souber, pode deixar tudo em branco.</p>
            <div className="space-y-3">
              <label className="flex items-start gap-2 cursor-pointer p-3 rounded border border-border">
                <Checkbox checked={state.tem_pdm_com_parametros} onCheckedChange={(v) => set("tem_pdm_com_parametros", !!v)} data-testid="autorizacao-pdm-params" />
                <span className="text-sm leading-relaxed">O terreno está em zona com <strong>plano de pormenor, unidade de execução ou operação de loteamento</strong> em vigor com parâmetros definidos.</span>
              </label>
              <label className="flex items-start gap-2 cursor-pointer p-3 rounded border border-border">
                <Checkbox checked={state.zona_urbana_consolidada} onCheckedChange={(v) => set("zona_urbana_consolidada", !!v)} data-testid="autorizacao-zuc" />
                <span className="text-sm leading-relaxed">O terreno está em <strong>zona urbana consolidada</strong> (malha urbana definida, infraestruturas e alinhamentos).</span>
              </label>
              <label className="flex items-start gap-2 cursor-pointer p-3 rounded border border-border">
                <Checkbox checked={state.tem_loteamento_pip} onCheckedChange={(v) => set("tem_loteamento_pip", !!v)} data-testid="autorizacao-pip" />
                <span className="text-sm leading-relaxed">Existe <strong>informação prévia favorável</strong> válida ou alvará de loteamento emitido para a parcela.</span>
              </label>
            </div>
          </section>
        )}

        {step === 5 && (
          <section data-testid="autorizacao-step-pdm-valores">
            <h2 className="text-xl sm:text-2xl font-semibold mb-1">Parâmetros do PDM (opcional)</h2>
            <p className="text-sm text-muted-foreground mb-5">Se consultou o PDM, introduza os limites — iremos verificar se o seu projeto cumpre.</p>
            <div className="space-y-3">
              <div>
                <Label htmlFor="pdm-h">Altura máxima permitida (m)</Label>
                <Input id="pdm-h" type="number" inputMode="decimal" step="0.1" min="0" value={state.pdm_altura_max_m ?? ""}
                       onChange={(e) => set("pdm_altura_max_m", e.target.value ? parseFloat(e.target.value) : null)}
                       data-testid="autorizacao-pdm-h" />
              </div>
              <div>
                <Label htmlFor="pdm-i">Índice de implantação máximo (0-1)</Label>
                <Input id="pdm-i" type="number" inputMode="decimal" step="0.01" min="0" max="1" value={state.pdm_indice_implantacao ?? ""}
                       onChange={(e) => set("pdm_indice_implantacao", e.target.value ? parseFloat(e.target.value) : null)}
                       data-testid="autorizacao-pdm-i" />
              </div>
              <div>
                <Label htmlFor="pdm-a">Afastamento mínimo às extremas (m)</Label>
                <Input id="pdm-a" type="number" inputMode="decimal" step="0.1" min="0" value={state.pdm_afastamento_min_m ?? ""}
                       onChange={(e) => set("pdm_afastamento_min_m", e.target.value ? parseFloat(e.target.value) : null)}
                       data-testid="autorizacao-pdm-a" />
              </div>
            </div>
          </section>
        )}

        {step === 6 && (
          <section data-testid="autorizacao-step-resumo">
            <h2 className="text-xl sm:text-2xl font-semibold mb-1">Resumo</h2>
            <p className="text-sm text-muted-foreground mb-5">Reveja antes de obter o diagnóstico.</p>
            <Card className="p-4 text-sm space-y-1">
              <div><strong>Tipo:</strong> {TIPOS.find((t) => t.v === state.tipo_obra)?.label || "-"}</div>
              {state.concelho && <div><strong>Concelho:</strong> {state.concelho}</div>}
              {!!state.altura_m && <div><strong>Altura:</strong> {state.altura_m} m</div>}
              {!!state.area_implantacao_m2 && <div><strong>Área de implantação:</strong> {state.area_implantacao_m2} m²</div>}
              {state.imovel_classificado && <div className="text-amber-700">⚠ Imóvel classificado</div>}
              {state.zona_protegida && <div className="text-amber-700">⚠ Zona protegida</div>}
            </Card>
            {error && <p className="text-sm text-rose-700 mt-4" data-testid="autorizacao-erro">{error}</p>}
          </section>
        )}

        <div className="flex items-center gap-3 mt-7">
          {step > 0 && (
            <Button variant="outline" onClick={() => setStep((s) => s - 1)} className="flex-1" data-testid="autorizacao-btn-anterior">
              <ArrowLeft size={16} /> Anterior
            </Button>
          )}
          {step < TOTAL_STEPS - 1 && (
            <Button onClick={() => setStep((s) => s + 1)} disabled={!canNext} className="flex-1" data-testid="autorizacao-btn-seguinte">
              Seguinte <ArrowRight size={16} />
            </Button>
          )}
          {step === TOTAL_STEPS - 1 && (
            <Button onClick={submit} disabled={loading} className="flex-1" data-testid="autorizacao-btn-diagnosticar">
              {loading ? "A calcular…" : "Obter diagnóstico"}
            </Button>
          )}
        </div>
      </div>
    </>
  );
}

// --------------------------------------------------------------------------
// Preparação do processo (Lote N2)
// --------------------------------------------------------------------------

function _downloadBase64(b64, filename, mime) {
  const bin = atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  const blob = new Blob([arr], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

function DossierBlock({ respostas, diagnostico }) {
  const [open, setOpen] = useState(false);
  const [requerente, setRequerente] = useState({ nome: "", nif: "", morada: "", telefone: "", email: "" });
  const [memoriaTexto, setMemoriaTexto] = useState("");
  const [memoriaLoading, setMemoriaLoading] = useState(false);
  const [dossier, setDossier] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [checklist, setChecklist] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (!open) return;
    fetch(`${API}/api/particulares/autorizacao/checklist`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ respostas, diagnostico }),
    }).then((r) => r.json()).then((d) => setChecklist(d)).catch(() => {});
  }, [open, respostas, diagnostico]);

  const previewMemoria = async () => {
    setMemoriaLoading(true); setErr(null);
    try {
      const r = await fetch(`${API}/api/particulares/autorizacao/memoria/preview`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ respostas, diagnostico }),
      });
      const d = await r.json();
      setMemoriaTexto(d.memoria_texto || "");
    } catch (e) {
      setErr("Não foi possível gerar a memória.");
    } finally {
      setMemoriaLoading(false);
    }
  };

  const gerarProcesso = async () => {
    setGenerating(true); setErr(null);
    try {
      const r = await fetch(`${API}/api/particulares/autorizacao/dossier/gerar`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          respostas, diagnostico, requerente,
          memoria_override: memoriaTexto || undefined,
          pecas: [],
        }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setDossier(d);
    } catch (e) {
      setErr("Não foi possível gerar o processo.");
    } finally {
      setGenerating(false);
    }
  };

  if (!open) {
    return (
      <div className="mt-8 pt-6 border-t">
        <h3 className="text-lg font-semibold mb-2 flex items-center gap-2"><Package size={20} /> Preparar o processo</h3>
        <p className="text-sm text-muted-foreground mb-3">
          Gere automaticamente o requerimento, a memória descritiva, a ficha de elementos
          estatísticos e a estimativa orçamental — tudo num só PDF e num ZIP com os ficheiros separados.
        </p>
        <p className="text-xs rounded border border-amber-200 bg-amber-50/60 p-3 mb-4" data-testid="autorizacao-aviso-venda">
          <strong>Pré-visualização gratuita.</strong> A venda do processo está temporariamente desativada;
          nesta fase pode gerar o processo sem custos para verificar o resultado.
        </p>
        <Button onClick={() => setOpen(true)} data-testid="autorizacao-preparar-processo">Preparar o meu processo</Button>
      </div>
    );
  }

  return (
    <div className="mt-8 pt-6 border-t" data-testid="autorizacao-dossier-bloco">
      <h3 className="text-lg font-semibold mb-4 flex items-center gap-2"><Package size={20} /> Preparar o processo</h3>

      <Card className="p-4 mb-4">
        <h4 className="font-medium mb-3">Identificação do requerente</h4>
        <div className="grid gap-3 sm:grid-cols-2">
          <div><Label htmlFor="r-nome">Nome</Label><Input id="r-nome" value={requerente.nome} onChange={(e) => setRequerente({ ...requerente, nome: e.target.value })} data-testid="autorizacao-req-nome" /></div>
          <div><Label htmlFor="r-nif">NIF</Label><Input id="r-nif" value={requerente.nif} onChange={(e) => setRequerente({ ...requerente, nif: e.target.value })} data-testid="autorizacao-req-nif" /></div>
          <div className="sm:col-span-2"><Label htmlFor="r-morada">Morada</Label><Input id="r-morada" value={requerente.morada} onChange={(e) => setRequerente({ ...requerente, morada: e.target.value })} data-testid="autorizacao-req-morada" /></div>
          <div><Label htmlFor="r-tel">Telefone</Label><Input id="r-tel" value={requerente.telefone} onChange={(e) => setRequerente({ ...requerente, telefone: e.target.value })} data-testid="autorizacao-req-tel" /></div>
          <div><Label htmlFor="r-email">E-mail</Label><Input id="r-email" type="email" value={requerente.email} onChange={(e) => setRequerente({ ...requerente, email: e.target.value })} data-testid="autorizacao-req-email" /></div>
        </div>
      </Card>

      <Card className="p-4 mb-4">
        <div className="flex items-center justify-between mb-2">
          <h4 className="font-medium">Memória descritiva</h4>
          <Button variant="outline" size="sm" onClick={previewMemoria} disabled={memoriaLoading} data-testid="autorizacao-memoria-preview">
            {memoriaLoading ? "A redigir…" : (memoriaTexto ? "Regenerar" : "Pré-visualizar")}
          </Button>
        </div>
        <p className="text-xs text-muted-foreground mb-2">A memória é gerada automaticamente a partir das suas respostas. Pode editá-la antes de gerar o PDF final.</p>
        <Textarea value={memoriaTexto} onChange={(e) => setMemoriaTexto(e.target.value)} rows={8}
                  placeholder="(Clique em «Pré-visualizar» para gerar o texto)" data-testid="autorizacao-memoria-texto" />
      </Card>

      {checklist && (
        <Card className="p-4 mb-4" data-testid="autorizacao-checklist">
          <h4 className="font-medium mb-2">Checklist de peças ({checklist.carregadas || 0}/{checklist.total})</h4>
          <ul className="space-y-1 text-sm">
            {(checklist.pecas || []).map((p, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className={p.carregada ? "text-emerald-600" : "text-muted-foreground"}>
                  {p.carregada ? "✓" : "•"}
                </span>
                <span className={p.carregada ? "" : "text-foreground/80"}>{p.peca}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {err && <p className="text-sm text-rose-700 mb-3" data-testid="autorizacao-dossier-erro">{err}</p>}

      {!dossier ? (
        <Button onClick={gerarProcesso} disabled={generating} data-testid="autorizacao-dossier-gerar">
          {generating ? "A gerar…" : "Gerar o processo"}
        </Button>
      ) : (
        <Card className="p-4 border-emerald-200 bg-emerald-50/40" data-testid="autorizacao-dossier-pronto">
          <h4 className="font-semibold mb-3 flex items-center gap-2 text-emerald-900">
            <CheckCircle2 size={18} /> Processo pronto
          </h4>
          <p className="text-sm mb-3">Inclui: {(dossier.ficheiros || []).join(", ")}</p>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => _downloadBase64(dossier.pdf_unico_b64, "processo-autorizacao.pdf", "application/pdf")}
                    data-testid="autorizacao-descarga-pdf">
              <Download size={16} /> PDF único
            </Button>
            <Button variant="outline"
                    onClick={() => _downloadBase64(dossier.zip_b64, "processo-autorizacao.zip", "application/zip")}
                    data-testid="autorizacao-descarga-zip">
              <Download size={16} /> ZIP (ficheiros separados)
            </Button>
          </div>
          <p className="text-xs text-muted-foreground mt-4">
            Lembre-se: a submissão oficial é feita exclusivamente através da PEPU ou do balcão único eletrónico do município.
          </p>
          <SubscreverBloco dossier={{ dossier_id: dossier.version, procedimento: diagnostico?.procedimento,
                                       regra_aplicada: diagnostico?.regra_aplicada,
                                       titulo_regra: diagnostico?.titulo_regra }}
                            especialidadesSugeridas={diagnostico?.tecnicos_obrigatorios || []}
                            requerenteEmail={requerente.email}
                            requerenteNome={requerente.nome} />
        </Card>
      )}
    </div>
  );
}


function SubscreverBloco({ dossier, especialidadesSugeridas, requerenteEmail, requerenteNome }) {
  const [tecnicos, setTecnicos] = useState([]);
  const [catalogoVazio, setCatalogoVazio] = useState(false);
  const [enviado, setEnviado] = useState(null);
  const [filtroEsp, setFiltroEsp] = useState(especialidadesSugeridas?.[0] || "arquitetura");
  const [loading, setLoading] = useState(false);
  const [custom, setCustom] = useState({ nome: "", email: "", especialidade: "arquitetura", numero: "" });
  const [modoCustom, setModoCustom] = useState(false);

  useEffect(() => {
    const esp = filtroEsp === "engenheiro_civil_ou_eletrotecnico" ? "engenheiro_civil" : filtroEsp;
    fetch(`${API}/api/particulares/autorizacao/tecnicos?especialidade=${encodeURIComponent(esp)}`)
      .then((r) => r.json())
      .then((d) => { setTecnicos(d.tecnicos || []); setCatalogoVazio(!!d.catalogo_vazio); })
      .catch(() => { setTecnicos([]); setCatalogoVazio(true); });
  }, [filtroEsp]);

  const pedir = async (tecnico_id, tecnico_custom) => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/particulares/autorizacao/subscricao/pedir`, {
        method: "POST", headers: { "Content-Type": "application/json" }, credentials: "include",
        body: JSON.stringify({
          tecnico_id: tecnico_id || null,
          tecnico_custom: tecnico_custom || null,
          requerente_email: requerenteEmail || null,
          requerente_nome: requerenteNome || null,
          dossier,
        }),
      });
      const d = await r.json();
      if (d.ok) setEnviado(d);
    } finally { setLoading(false); }
  };

  if (enviado) {
    const link = `${window.location.origin}${enviado.link_subscrever || "/subscrever/" + enviado.signing_token}`;
    return (
      <div className="mt-5 p-4 rounded border border-emerald-200 bg-emerald-50/60" data-testid="autorizacao-subscricao-ok">
        <p className="font-medium mb-1">Pedido enviado a {enviado.tecnico.nome}</p>
        <p className="text-sm text-muted-foreground mb-2">
          {enviado.email_enviado
            ? "O técnico recebeu o link por e-mail. Pode também partilhá-lo diretamente:"
            : "O e-mail automático não pôde ser enviado — partilhe este link diretamente com o técnico:"}
        </p>
        <code className="block text-xs break-all p-2 bg-background border rounded" data-testid="autorizacao-subscricao-link">{link}</code>
        <p className="text-xs text-muted-foreground mt-2">Link válido durante 30 dias.</p>
      </div>
    );
  }

  const mostrarCustom = catalogoVazio || tecnicos.length === 0 || modoCustom;

  return (
    <div className="mt-6 pt-5 border-t" data-testid="autorizacao-subscricao-bloco">
      <h4 className="font-semibold mb-2">Pedir subscrição a um técnico</h4>

      {catalogoVazio && (
        <p className="text-sm text-amber-800 bg-amber-50/60 border border-amber-200 rounded p-3 mb-3" data-testid="autorizacao-catalogo-vazio">
          Ainda não temos técnicos parceiros nesta região. Pode indicar o <strong>seu</strong> arquiteto ou
          engenheiro para subscrever o processo.
        </p>
      )}

      {!catalogoVazio && (
        <>
          <div className="flex items-center gap-2 mb-3">
            <label className="text-sm">Especialidade:</label>
            <select value={filtroEsp} onChange={(e) => setFiltroEsp(e.target.value)}
                    className="border rounded h-9 px-2 text-sm bg-background" data-testid="autorizacao-subscricao-esp">
              <option value="arquitetura">Arquitetura</option>
              <option value="engenheiro_estruturas">Engenharia de estruturas</option>
              <option value="engenheiro_civil">Engenharia civil</option>
              <option value="engenheiro_eletrotecnico">Engenharia eletrotécnica</option>
              <option value="coordenador_projeto">Coordenação de projeto</option>
            </select>
          </div>
          <div className="grid gap-2 mb-3">
            {tecnicos.map((t) => (
              <div key={t.id} className="flex items-center justify-between p-3 rounded border" data-testid={`autorizacao-tecnico-${t.id}`}>
                <div className="text-sm">
                  <div className="font-medium">{t.nome}</div>
                  <div className="text-xs text-muted-foreground">{t.ordem} {t.numero} · {t.regiao} · ~{t.prazo_dias || 7} dias · {t.preco_indicativo_eur || 0} €</div>
                </div>
                <Button size="sm" onClick={() => pedir(t.id, null)} disabled={loading} data-testid={`autorizacao-tecnico-pedir-${t.id}`}>Pedir</Button>
              </div>
            ))}
          </div>
          <Button variant="outline" size="sm" onClick={() => setModoCustom(!modoCustom)} data-testid="autorizacao-tecnico-custom-toggle">
            {modoCustom ? "Esconder" : "Indicar o meu próprio técnico"}
          </Button>
        </>
      )}

      {mostrarCustom && (
        <div className="mt-3 p-3 rounded border bg-muted/30" data-testid="autorizacao-tecnico-custom">
          <h5 className="font-medium mb-2 text-sm">Indicar o meu arquiteto / engenheiro</h5>
          <div className="grid gap-2 sm:grid-cols-2">
            <div><Label className="text-xs">Nome*</Label>
              <Input value={custom.nome} onChange={(e) => setCustom({ ...custom, nome: e.target.value })} data-testid="autorizacao-custom-nome" />
            </div>
            <div><Label className="text-xs">E-mail*</Label>
              <Input type="email" value={custom.email} onChange={(e) => setCustom({ ...custom, email: e.target.value })} data-testid="autorizacao-custom-email" />
            </div>
            <div><Label className="text-xs">Especialidade</Label>
              <select value={custom.especialidade} onChange={(e) => setCustom({ ...custom, especialidade: e.target.value })}
                      className="w-full border rounded h-10 px-2 bg-background" data-testid="autorizacao-custom-esp">
                <option value="arquitetura">Arquiteto</option>
                <option value="engenheiro_estruturas">Engenheiro de estruturas</option>
                <option value="engenheiro_civil">Engenheiro civil</option>
                <option value="engenheiro_eletrotecnico">Engenheiro eletrotécnico</option>
                <option value="engenheiro_mecanico">Engenheiro mecânico</option>
                <option value="coordenador_projeto">Coordenador de projeto</option>
              </select>
            </div>
            <div><Label className="text-xs">Nº da ordem (opcional)</Label>
              <Input value={custom.numero} onChange={(e) => setCustom({ ...custom, numero: e.target.value })} data-testid="autorizacao-custom-numero" />
            </div>
          </div>
          <Button size="sm" className="mt-3"
                  disabled={!custom.nome || !custom.email || !custom.email.includes("@") || loading}
                  onClick={() => pedir(null, custom)}
                  data-testid="autorizacao-custom-enviar">
            Enviar pedido de subscrição
          </Button>
        </div>
      )}
    </div>
  );
}

