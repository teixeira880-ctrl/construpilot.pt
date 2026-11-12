// GeometriaPanel — leitura automática da geometria (motor geometria-v3): divisões fechadas pelas paredes, escala por
// consenso, confiança por divisão (verde / laranja / vermelho) e correções do utilizador (guardadas para treino).
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { Loader2, ScanLine, CheckCircle2, AlertTriangle, XCircle, Flag } from "lucide-react";

const NIVEL = {
  verde: { cls: "bg-emerald-600 text-white", icon: CheckCircle2, txt: "Confirmada" },
  laranja: { cls: "bg-amber-500 text-white", icon: AlertTriangle, txt: "A verificar" },
  vermelho: { cls: "bg-red-600 text-white", icon: XCircle, txt: "Incoerente" },
};
const ESCALA = {
  confirmada: "Escala confirmada",
  fonte_unica: "Escala de uma só fonte",
  conflito: "Escalas em desacordo",
  desconhecida: "Escala desconhecida",
};
const CORRECOES = [
  ["forma_errada", "Contorno errado"],
  ["area_errada", "Área errada"],
  ["mal_identificado", "Nome errado"],
  ["nao_existe", "Não é uma divisão"],
];

const errMsg = (e, fb) => e?.response?.data?.detail || fb;

export default function GeometriaPanel({ planId, pageIndex, onOverlay, onApplied }) {
  const [res, setRes] = useState(null);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [aberta, setAberta] = useState(null);

  useEffect(() => {
    let vivo = true;
    setRes(null); onOverlay?.(null);
    if (!planId) return undefined;
    api.get(`/takeoffs/${planId}/geometria?page_index=${pageIndex}`)
      .then(({ data }) => { if (vivo) { setRes(data); onOverlay?.(data); } })
      .catch(() => {});
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planId, pageIndex]);

  const analisar = async () => {
    setLoading(true);
    try {
      const { data } = await api.post(`/takeoffs/${planId}/geometria?page_index=${pageIndex}`);
      setRes(data); onOverlay?.(data);
      if (!data.ok) toast.warning(data.mensagem || "Nenhuma divisão fechada encontrada nesta página");
      else toast.success(`${data.divisoes.length} divisão(ões) lida(s) — ${data.area_util_m2} m² úteis`);
    } catch (e) { toast.error(errMsg(e, "Análise geométrica impossível")); }
    finally { setLoading(false); }
  };

  const aplicar = async () => {
    setApplying(true);
    try {
      const { data } = await api.post(`/takeoffs/${planId}/geometria/aplicar`, { page_index: pageIndex, divisoes: [] });
      toast.success(`${data.aplicadas} divisão(ões) aplicada(s) às medições`);
      onApplied?.();
    } catch (e) { toast.error(errMsg(e, "Impossível aplicar as divisões")); }
    finally { setApplying(false); }
  };

  const corrigir = async (d, tipo) => {
    let extra = {};
    if (tipo === "area_errada") {
      const v = window.prompt(`Área correta de « ${d.nome} » (m²)?`, String(d.area_m2));
      if (v === null) return;
      const n = parseFloat(String(v).replace(",", "."));
      if (!Number.isFinite(n) || n <= 0) { toast.error("Área inválida"); return; }
      extra.area_correta_m2 = n;
    }
    if (tipo === "mal_identificado") {
      const v = window.prompt("Nome correto da divisão?", d.nome);
      if (!v) return;
      extra.nome_correto = v.slice(0, 120);
    }
    try {
      await api.post(`/takeoffs/${planId}/geometria/correcao`, { page_index: pageIndex, tipo, divisao_id: d.id, ...extra });
      toast.success("Obrigado — a correção fica registada e melhora as próximas leituras");
      setAberta(null);
    } catch (e) { toast.error(errMsg(e, "Correção não registada")); }
  };

  const falta = async () => {
    try {
      await api.post(`/takeoffs/${planId}/geometria/correcao`, { page_index: pageIndex, tipo: "falta" });
      toast.success("Registado: falta uma divisão nesta página");
    } catch (e) { toast.error(errMsg(e, "Correção não registada")); }
  };

  const esc = res?.escala || {};
  return (
    <div className="border border-border rounded-sm p-3 grid gap-2" data-testid="geometria-panel">
      <div className="flex items-center justify-between gap-2">
        <p className="font-bold text-sm flex items-center gap-1"><ScanLine className="h-4 w-4" /> Leitura automática da geometria</p>
        <Button size="sm" className="rounded-sm" onClick={analisar} disabled={loading || !planId} data-testid="geometria-analisar">
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : (res ? "Reanalisar" : "Analisar")}
        </Button>
      </div>
      {!res && !loading && (
        <p className="text-xs text-muted-foreground">
          Lê as divisões fechadas pelas paredes, a escala (por várias fontes), as paredes e os vãos, sem IA, e diz quanto pode confiar em cada número.
        </p>
      )}
      {res && (
        <>
          <div className="flex flex-wrap gap-1 text-[11px]">
            <Badge variant="outline" className={esc.estado === "confirmada" ? "border-emerald-600 text-emerald-700" : esc.estado === "fonte_unica" ? "border-amber-500 text-amber-700" : "border-red-600 text-red-700"}>
              {ESCALA[esc.estado] || "Escala"}
            </Badge>
            <Badge variant="outline">{res.fonte === "dxf" ? "DWG/DXF" : res.fonte === "pdf_vetorial" ? "PDF vetorial" : "Imagem"}</Badge>
            {res.confianca?.resumo && Object.entries(res.confianca.resumo).filter(([, n]) => n).map(([k, n]) => (
              <Badge key={k} className={NIVEL[k].cls}>{n} {NIVEL[k].txt.toLowerCase()}</Badge>
            ))}
          </div>
          {esc.mensagem && <p className="text-[11px] text-muted-foreground">{esc.mensagem}</p>}
          {res.ok && (
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
              <span className="text-muted-foreground">Área útil</span><span className="num text-right font-bold">{res.area_util_m2} m²</span>
              <span className="text-muted-foreground">Implantação</span><span className="num text-right">{res.area_implantacao_m2} m²</span>
              {res.paredes?.exteriores_eixo_m != null && <><span className="text-muted-foreground">Paredes exteriores (eixo)</span><span className="num text-right">{res.paredes.exteriores_eixo_m} m · {Math.round((res.paredes.espessura_exterior_m || 0) * 100)} cm</span></>}
              {res.paredes?.interiores_por_espessura_m && Object.entries(res.paredes.interiores_por_espessura_m).map(([t, l]) => (
                <span key={t} className="contents"><span className="text-muted-foreground">Divisórias {Math.round(parseFloat(t) * 100)} cm</span><span className="num text-right">{l} m</span></span>
              ))}
              {res.vaos && <><span className="text-muted-foreground">Vãos (indicativo)</span><span className="num text-right">{res.vaos.portas} portas · {res.vaos.janelas} janelas</span></>}
            </div>
          )}
          {(res.verificacoes || []).length > 0 && (
            <ul className="text-[11px] grid gap-0.5">
              {res.verificacoes.map((v) => (
                <li key={v.id} className={v.ok ? "text-emerald-700" : "text-red-700"}>{v.ok ? "✓" : "✗"} {v.texto}</li>
              ))}
            </ul>
          )}
          <div className="grid gap-1">
            {(res.divisoes || []).map((d) => {
              const N = NIVEL[d.nivel] || NIVEL.laranja;
              const Icon = N.icon;
              return (
                <div key={d.id} className="border border-border rounded-sm p-2 text-xs" data-testid={`geometria-div-${d.id}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold flex items-center gap-1"><Icon className={`h-3 w-3 ${d.nivel === "verde" ? "text-emerald-600" : d.nivel === "vermelho" ? "text-red-600" : "text-amber-500"}`} />{d.nome}</span>
                    <span className="num font-bold">{d.area_m2.toFixed(2)} m²</span>
                  </div>
                  {(d.motivos || []).length > 0 && <p className="text-[10px] text-muted-foreground mt-0.5">{d.motivos.join(" · ")}</p>}
                  <button type="button" className="text-[10px] underline text-muted-foreground mt-1 flex items-center gap-1" onClick={() => setAberta(aberta === d.id ? null : d.id)}>
                    <Flag className="h-3 w-3" /> Reportar um erro
                  </button>
                  {aberta === d.id && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {CORRECOES.map(([t, lbl]) => (
                        <Button key={t} size="sm" variant="outline" className="h-6 text-[10px] rounded-sm" onClick={() => corrigir(d, t)}>{lbl}</Button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          {res.ok && (
            <div className="flex gap-2">
              <Button size="sm" className="flex-1 rounded-sm" onClick={aplicar} disabled={applying || ["conflito", "desconhecida"].includes(esc.estado)} data-testid="geometria-aplicar">
                {applying ? <Loader2 className="h-3 w-3 animate-spin" /> : "Aplicar às medições"}
              </Button>
              <Button size="sm" variant="outline" className="rounded-sm" onClick={falta}>Falta uma divisão</Button>
            </div>
          )}
          {res.fonte === "imagem" && (
            <p className="text-[10px] text-muted-foreground">Planta em imagem: para a melhor precisão, use o PDF ou o DWG originais, ou uma digitalização a 300 dpi.</p>
          )}
        </>
      )}
    </div>
  );
}
