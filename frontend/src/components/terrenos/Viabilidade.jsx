import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import { AlertTriangle, Box, Building2, CheckCircle2, Download, FileUp, Info, Loader2, ShieldAlert, Sun, Wind } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api, num } from "@/lib/api";

/**
 * Viabilidade construtiva do terreno: relevo, sol, acessibilidade, riscos naturais, PDM/REN/RAN, conforto térmico,
 * potencial construtivo e implantação recomendada — com relatório PDF, IFC do terreno e IFC do projeto implantado.
 */

const CLASSE_COR = {
  viavel: "bg-emerald-600", viavel_com_condicionantes: "bg-amber-500", condicionada: "bg-orange-600", inviavel_provavel: "bg-red-600",
};
const NIVEL_COR = {
  baixo: "text-emerald-600 border-emerald-500/50", moderado: "text-amber-600 border-amber-500/50",
  elevado: "text-orange-600 border-orange-500/50", muito_elevado: "text-red-600 border-red-500/50", por_confirmar: "text-slate-500 border-slate-400/50",
};
const RISCO_NOME = { incendio_rural: "Incêndio rural", cheias_inundacoes: "Cheias e inundações", erosao_hidrica: "Erosão hídrica", movimentos_vertente: "Movimentos de vertente" };
const FUND_COR = { critico: "text-red-600", aviso: "text-amber-600", ok: "text-emerald-600", info: "text-muted-foreground" };
const PDM = [
  ["iu_max", "Iu máx. (m²/m²)"], ["io_max_pct", "Io máx. (%)"], ["n_pisos_max", "Pisos máx."], ["altura_fachada_max_m", "Cércea (m)"],
  ["afastamento_frontal_min_m", "Afast. frontal (m)"], ["afastamento_lateral_min_m", "Afast. lateral (m)"], ["afastamento_tardoz_min_m", "Afast. tardoz (m)"],
];
const RUMOS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"];
const rumo = (a) => (a == null ? "—" : RUMOS[Math.floor((((a % 360) + 11.25) % 360) / 22.5)]);
const erroTxt = (e, d) => (typeof e?.response?.data?.detail === "string" ? e.response.data.detail : d);

async function blobErro(e) {
  try { const t = await e?.response?.data?.text?.(); return JSON.parse(t).detail; } catch { return null; }
}

export default function Viabilidade({ terrenoId, anel, nome, mapa }) {
  const [pdm, setPdm] = useState({});
  const [ed, setEd] = useState({ largura_m: "", profundidade_m: "", n_pisos: "" });
  const [modelo, setModelo] = useState(null);
  const [res, setRes] = useState(null);
  const [ocupado, setOcupado] = useState("");
  const [erro, setErro] = useState(null);
  const [camada, setCamada] = useState("implantacao");
  const grupo = useRef(null);
  const fich = useRef(null);

  const corpo = () => {
    const p = Object.fromEntries(Object.entries(pdm).filter(([, v]) => v !== "" && v != null).map(([k, v]) => [k, Number(v)]));
    const e = Object.fromEntries(Object.entries(ed).filter(([, v]) => v !== "").map(([k, v]) => [k, Number(v)]));
    return {
      ...(terrenoId ? { terreno_id: terrenoId } : { anel_latlon: anel }), nome: nome || "", pdm: p,
      edificio: Object.keys(e).length ? e : null, modelo_id: modelo?.modelo_id || null,
    };
  };

  // terreno diferente → resultado antigo deixa de valer
  useEffect(() => { setRes(null); setErro(null); }, [terrenoId, JSON.stringify(anel)]);  // eslint-disable-line react-hooks/exhaustive-deps

  // camadas no mapa
  useEffect(() => {
    const m = mapa?.current;
    if (!m) return undefined;
    if (!grupo.current) grupo.current = L.layerGroup().addTo(m);
    const g = grupo.current;
    g.clearLayers();
    if (!res) return undefined;
    if (camada === "aptidao" || camada === "irradiacao") {
      const c = res.camadas?.[camada];
      if (c) L.imageOverlay(c.png, c.bounds, { opacity: 0.75, interactive: false }).addTo(g);
    }
    (res.zona_livre?.aneis_latlon || []).forEach((a) => L.polygon(a, { color: "#40c057", weight: 1.5, dashArray: "4 3", fillOpacity: camada === "implantacao" ? 0.12 : 0, interactive: false }).addTo(g));
    (res.relevo?.linhas_agua || []).forEach((l) => L.polyline(l.latlon, { color: "#1c7ed6", weight: 2, interactive: false }).addTo(g));
    const im = res.implantacao;
    if (im?.ok) {
      L.polygon(im.poligono_latlon, { color: "#0f6e4f", weight: 2, fillColor: "#0f6e4f", fillOpacity: 0.55 })
        .bindTooltip(`Implantação recomendada · ${num(im.largura_m, 1)} × ${num(im.profundidade_m, 1)} m · soleira ${num(im.cota_soleira_sugerida, 2)} m`)
        .addTo(g);
      const [la, lo] = im.centro_latlon;
      const az = (im.azimute_fachada_principal * Math.PI) / 180;
      const d = (Math.max(im.largura_m, im.profundidade_m) * 0.9) / 111320;
      L.polyline([[la, lo], [la + d * Math.cos(az), lo + (d * Math.sin(az)) / Math.cos((la * Math.PI) / 180)]], { color: "#f59f00", weight: 3, interactive: false }).addTo(g);
    }
    if (res.acessibilidade?.ponto_via_latlon) L.circleMarker(res.acessibilidade.ponto_via_latlon, { radius: 5, color: "#495057", fillOpacity: 1 }).bindTooltip(res.acessibilidade.via || "Via de acesso").addTo(g);
    return undefined;
  }, [res, camada, mapa]);
  useEffect(() => () => { if (grupo.current && mapa?.current) mapa.current.removeLayer(grupo.current); grupo.current = null; }, [mapa]);

  const avaliar = async () => {
    setOcupado("avaliar"); setErro(null);
    try {
      const { data } = await api.post("/viabilidade/avaliar", corpo(), { timeout: 240000 });
      setRes(data);
    } catch (e) { setErro(erroTxt(e, "Não foi possível avaliar o terreno.")); }
    setOcupado("");
  };

  const baixar = async (path, ficheiro, k) => {
    setOcupado(k); setErro(null);
    try {
      const r = await api.post(path, corpo(), { responseType: "blob", timeout: 240000 });
      const u = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = u; a.download = ficheiro; a.click();
      setTimeout(() => URL.revokeObjectURL(u), 4000);
    } catch (e) { setErro((await blobErro(e)) || "Não foi possível gerar o ficheiro."); }
    setOcupado("");
  };

  const carregarIfc = async (f) => {
    if (!f) return;
    setOcupado("ifc"); setErro(null);
    try {
      const fd = new FormData(); fd.append("ficheiro", f);
      const { data } = await api.post("/viabilidade/modelo", fd, { timeout: 180000 });
      setModelo(data);
      setEd({ largura_m: data.largura_m, profundidade_m: data.profundidade_m, n_pisos: data.n_pisos });
    } catch (e) { setErro(erroTxt(e, "Não foi possível ler o IFC.")); }
    setOcupado("");
    if (fich.current) fich.current.value = "";
  };

  const base = (nome || "terreno").replace(/[^\w-]+/g, "_");
  const v = res?.viabilidade;

  return (
    <Card className="p-3 space-y-3 text-sm" data-testid="terrenos-viabilidade">
      <div className="flex items-center gap-2 font-medium"><Building2 className="h-4 w-4 text-primary" /> Viabilidade construtiva</div>
      <details className="rounded border p-2">
        <summary className="cursor-pointer text-xs font-semibold text-muted-foreground">Parâmetros do PDM (regulamento municipal) — opcional</summary>
        <div className="grid grid-cols-2 gap-2 mt-2">
          {PDM.map(([k, t]) => (
            <label key={k} className="text-[11px] text-muted-foreground">{t}
              <Input type="number" step="any" min="0" className="h-7 text-xs" value={pdm[k] ?? ""} onChange={(e) => setPdm((o) => ({ ...o, [k]: e.target.value }))} />
            </label>
          ))}
        </div>
        <p className="text-[11px] text-muted-foreground mt-1">Sem estes valores o potencial fica «sem dados»: nunca são inventados. Os afastamentos em falta usam pressupostos de estudo assinalados.</p>
      </details>
      <div className="grid grid-cols-3 gap-2">
        {[["largura_m", "Largura (m)"], ["profundidade_m", "Profund. (m)"], ["n_pisos", "Pisos"]].map(([k, t]) => (
          <label key={k} className="text-[11px] text-muted-foreground">{t}
            <Input type="number" step="any" min="0" className="h-7 text-xs" placeholder={k === "n_pisos" ? "2" : k === "largura_m" ? "12" : "10"} value={ed[k] ?? ""} onChange={(e) => setEd((o) => ({ ...o, [k]: e.target.value }))} />
          </label>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="outline" onClick={() => fich.current?.click()} disabled={ocupado === "ifc"}>
          {ocupado === "ifc" ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <FileUp className="h-4 w-4 mr-1" />} Usar o IFC do projeto
        </Button>
        <input ref={fich} type="file" accept=".ifc" className="hidden" onChange={(e) => carregarIfc(e.target.files?.[0])} />
        {modelo && <span className="text-xs text-muted-foreground">{modelo.nome}: {num(modelo.largura_m, 1)} × {num(modelo.profundidade_m, 1)} m · {modelo.n_pisos} piso(s) · {num(modelo.altura_m, 1)} m
          <button className="ml-1 opacity-60 hover:opacity-100" onClick={() => setModelo(null)}>×</button></span>}
      </div>
      <Button size="sm" onClick={avaliar} disabled={ocupado === "avaliar" || !(terrenoId || (anel && anel.length >= 3))} data-testid="viabilidade-avaliar">
        {ocupado === "avaliar" ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <CheckCircle2 className="h-4 w-4 mr-1" />} {res ? "Reavaliar" : "Avaliar viabilidade"}
      </Button>
      {ocupado === "avaliar" && <p className="text-xs text-muted-foreground">A obter o MDT, consultar PDM, REN, RAN e servidões (DGT), vias e edifícios vizinhos (OSM) e calcular sol, riscos e implantação… até 2 minutos.</p>}
      {erro && <p className="text-xs text-red-600 flex gap-1"><AlertTriangle className="h-4 w-4 shrink-0" /> {erro}</p>}

      {res && v && (
        <div className="space-y-3">
          <div className={`rounded-md p-2 text-white ${CLASSE_COR[v.classificacao] || "bg-slate-600"}`}>
            <div className="font-semibold">{v.rotulo}</div>
            <div className="text-xs opacity-90">Índice {v.indice}/100</div>
          </div>
          <ul className="space-y-1">
            {v.fundamentos.map((f, i) => <li key={i} className={`text-xs ${FUND_COR[f.nivel] || ""}`}>• {f.texto}</li>)}
          </ul>

          <div className="flex gap-1 text-[11px]">
            {[["implantacao", "Implantação"], ["aptidao", "Aptidão"], ["irradiacao", "Radiação solar"]].map(([k, t]) => (
              <button key={k} className={`px-2 py-1 rounded ${camada === k ? "bg-primary text-primary-foreground" : "bg-muted"}`} onClick={() => setCamada(k)}>{t}</button>
            ))}
          </div>

          <Secao titulo="Relevo" icon={Info}>
            <Linha k="Altitude" v={`${num(res.relevo.cota_min, 1)} – ${num(res.relevo.cota_max, 1)} m (média ${num(res.relevo.cota_media, 1)} m)`} />
            <Linha k="Declive médio / máx." v={`${num(res.relevo.declive_medio_pct, 1)} % / ${num(res.relevo.declive_max_pct, 1)} %`} />
            <Linha k="Vertentes" v={`dominante ${res.relevo.exposicao}`} />
            <Linha k="Forma" v={res.relevo.formas?.[0]?.descricao?.split(" — ")[0]} />
            <Linha k="MDT" v={`${res.mdt.fonte}${res.mdt.oficial ? "" : " (indicativo)"} · ${num(res.mdt.resolucao_analise_m, 1)} m`} />
          </Secao>

          <Secao titulo="Sol e conforto" icon={Sun}>
            <Linha k="Irradiação anual" v={`${num(res.solar.irradiacao_anual_kwh_m2.media, 0)} kWh/m² (índice ${num(res.solar.indice_solar_pct, 0)} %)`} />
            <Linha k="Sol a 21 dez." v={`${num(res.solar.horas_sol_21dez.media, 1)} h de ${num(res.solar.horas_sol_21dez.duracao_dia, 1)} h`} />
            <Linha k="Orientação" v={res.conforto.orientacao_recomendada.texto} />
            <Linha k="Sobreaquecimento" v={res.conforto.sobreaquecimento.nivel} />
            <Linha k={<span className="inline-flex items-center gap-1"><Wind className="h-3 w-3" /> Vento</span>} v={res.conforto.ventilacao.exposicao_vento_dominante} />
          </Secao>

          <Secao titulo="Riscos naturais" icon={ShieldAlert}>
            {res.riscos.riscos.map((e) => (
              <div key={e.risco} className="flex items-center justify-between gap-2">
                <span className="text-xs">{RISCO_NOME[e.risco] || e.risco}</span>
                <Badge variant="outline" className={`text-[10px] ${NIVEL_COR[e.nivel] || ""}`}>{e.rotulo}</Badge>
              </div>
            ))}
          </Secao>

          <Secao titulo="Ordenamento e potencial" icon={Building2}>
            <Linha k="PDM" v={`${res.ordenamento.solo.solo}${res.ordenamento.solo.categoria ? " · " + res.ordenamento.solo.categoria : ""}`} />
            <Linha k="REN / RAN" v={`${num(res.ordenamento.condicionantes.ren.fracao * 100, 1)} % / ${num(res.ordenamento.condicionantes.ran.fracao * 100, 1)} %`} />
            <Linha k="Zona livre" v={`${num(res.ordenamento.potencial.area_livre_para_implantacao_m2, 0)} m²`} />
            <Linha k="Implantação máx." v={res.ordenamento.potencial.area_implantacao_max_m2 != null ? `${num(res.ordenamento.potencial.area_implantacao_max_m2, 0)} m²` : "sem dados"} />
            <Linha k="Construção máx." v={res.ordenamento.potencial.area_construcao_max_m2 != null ? `${num(res.ordenamento.potencial.area_construcao_max_m2, 0)} m²` : "sem dados"} />
            <Linha k="Acesso" v={res.acessibilidade?.texto || "por confirmar"} />
          </Secao>

          {res.implantacao?.ok ? (
            <Secao titulo="Implantação recomendada" icon={Box}>
              <Linha k="Edifício" v={`${num(res.implantacao.largura_m, 1)} × ${num(res.implantacao.profundidade_m, 1)} m · ${res.implantacao.n_pisos} piso(s)`} />
              <Linha k="Fachada principal" v={`virada a ${rumo(res.implantacao.azimute_fachada_principal)}`} />
              <Linha k="Cota de soleira" v={`${num(res.implantacao.cota_soleira_sugerida, 2)} m · ${res.implantacao.solucao_desnivel}`} />
              <Linha k="Terras" v={`${num(res.implantacao.movimento_terras.escavacao_m3, 0)} m³ escavação · ${num(res.implantacao.movimento_terras.aterro_m3, 0)} m³ aterro`} />
            </Secao>
          ) : <p className="text-xs text-red-600">{res.implantacao?.nota}</p>}

          {res.verificacao_edificio?.length > 0 && (
            <div className="space-y-1">
              {res.verificacao_edificio.map((x) => (
                <div key={x.item} className={`text-xs ${x.resultado === "conforme" ? "text-emerald-600" : "text-red-600"}`}>
                  {x.item}: {num(x.valor, 1)} / {num(x.limite, 1)} — {x.resultado.replace("_", " ")}
                </div>
              ))}
            </div>
          )}

          <details className="rounded border p-2">
            <summary className="cursor-pointer text-xs font-semibold">Recomendações ({res.recomendacoes.length})</summary>
            <ul className="mt-1 space-y-1">{res.recomendacoes.map((r, i) => <li key={i} className="text-xs">• {r}</li>)}</ul>
          </details>

          <div className="flex flex-wrap gap-2 pt-1 border-t">
            <Button size="sm" variant="outline" disabled={!!ocupado} onClick={() => baixar("/viabilidade/relatorio.pdf", `viabilidade_${base}.pdf`, "pdf")}>
              {ocupado === "pdf" ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Download className="h-4 w-4 mr-1" />} Relatório PDF
            </Button>
            <Button size="sm" variant="outline" disabled={!!ocupado} onClick={() => baixar("/viabilidade/terreno.ifc", `terreno_${base}.ifc`, "tifc")}>
              {ocupado === "tifc" ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Box className="h-4 w-4 mr-1" />} IFC do terreno
            </Button>
            {modelo && res.implantacao?.ok && (
              <Button size="sm" variant="outline" disabled={!!ocupado} onClick={() => baixar("/viabilidade/modelo-implantado.ifc", `${(modelo.nome || "modelo").replace(/\.ifc$/i, "")}_implantado.ifc`, "mifc")}>
                {ocupado === "mifc" ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Box className="h-4 w-4 mr-1" />} Projeto IFC implantado
              </Button>
            )}
          </div>
          <p className="text-[11px] text-muted-foreground">{res.aviso_legal}</p>
        </div>
      )}
    </Card>
  );
}

function Secao({ titulo, icon: Icon, children }) {
  return (
    <div className="rounded border p-2 space-y-1">
      <div className="text-xs font-semibold flex items-center gap-1 text-muted-foreground"><Icon className="h-3.5 w-3.5" /> {titulo}</div>
      {children}
    </div>
  );
}

function Linha({ k, v }) {
  return (
    <div className="flex justify-between gap-2 text-xs">
      <span className="text-muted-foreground shrink-0">{k}</span>
      <span className="text-right">{v ?? "—"}</span>
    </div>
  );
}
