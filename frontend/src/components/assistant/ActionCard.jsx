import { useEffect, useId, useState } from "react";
import { Link } from "react-router-dom";
import { FileDown, Link2 } from "lucide-react";
import { toast } from "sonner";
import { eur } from "@/lib/api";
import { pollCotesJob } from "@/lib/cotesJobs";
import { CompareCard } from "./CompareCard";
import { WorkDraftCard } from "./WorkDraftCard";
import { QuoteDraftCard } from "./QuoteDraftCard";
import { useQuoteCopy } from "./quoteCopy";
import { ArtifactCard } from "./PrivateMedia";
import { useDocumentViewer } from "./DocumentViewer";
import { VerifiedSourceCard, ProductSearchCard, OptionsCompareCard } from "./SourceCards";

const TOOL_LABEL = {
  supervise_platform: "Controlo do processo lançado", get_supervision_result: "Estado do controlo",
  cancel_supervision: "Paragem do controlo pedida",
  list_platform_resources: "Documentos da conta", list_platform_calculators: "Calculadoras disponíveis", run_platform_calculator: "Cálculo de materiais",
  create_downloadable_file: "Ficheiro criado", read_generated_file: "Ficheiro relido", read_building_geometry: "Geometria lida (a validar)", generate_structural_execution_dossier: "Dossier estrutural",
  inspect_document_region: "Detalhe do documento consultado", read_work_draft: "Rascunho relido", update_work_draft: "Rascunho revisto",
  read_document: "Páginas consultadas", calculate: "Cálculo verificado", create_work_draft: "Rascunho editável", search_own_history: "As suas conversas encontradas",
  define_analysis_scope: "Âmbito de análise", analyze_plan: "Análise aprofundada iniciada", get_plan_results: "Resultados da planta lidos",
  generate_branded_pdf: "Relatório PDF", create_quote_draft: "Rascunho de orçamento", save_user_preference: "Preferência memorizada",
  create_project_task: "Tarefa criada", estimate_budget_range: "Estimativa orçamental indicativa", compare_documents: "Comparação de documentos",
  search_product_sources: "Documentação do produto pesquisada", fetch_verified_source: "Fonte consultada", compare_technical_options: "Soluções comparadas",
  check_dimension_chain: "Cadeia de cotas calculada", compare_dimension_values: "Cotas comparadas", resolve_ambiguous_reading: "Leitura ambígua examinada",
  classify_strokes: "Traços classificados", dedupe_elements: "Elementos sem duplicados", calculate_quantities: "Quantidades calculadas",
  read_rebar_schedule: "Lista de armaduras lida", read_native_dimensions: "Cotas nativas lidas",
  compute_concrete_volumes: "Volumes de betão calculados", update_project_state: "Estado do processo atualizado", draw_section_schema: "Esquema de princípio cotado desenhado",
};

function RebarCard({ r }) {
  const ha = r.native?.ha_bars, mesh = r.native?.mesh, recap = r.native?.mesh_recap, el = r.sheet?.element, chk = r.sheet?.checks;
  return (
    <div data-testid="assistant-rebar-card">
      {r.requires_vision && <div>Texto vetorizado: relance com leitura visual (chamada faturada).</div>}
      {ha && <div>Aços A500: {ha.count} marcas · massa teórica {ha.total_mass_kg} kg · {ha.inconsistencies?.length || 0} incoerência(s) aritmética(s)
        {ha.comparison && ` · diferença vs resumo ${ha.comparison.difference_kg > 0 ? "+" : ""}${ha.comparison.difference_kg} kg`}</div>}
      {mesh && <div>Malha: {mesh.count} painéis · {mesh.rows_mass_kg} kg{recap?.mass_laid_kg != null && ` · massa colocada ${recap.mass_laid_kg} kg`}</div>}
      {r.native?.partial && <div>Lista de armaduras marcada como «parcial» na folha.</div>}
      {el && <div>Folha {el.label || "?"} · Betão {el.concrete_m3 ?? "—"} m³ · Aço {el.steel_kg ?? "—"} kg · {chk?.inconsistencies?.length || 0} diferença(s) Comp./Peso · leitura visual a verificar</div>}
    </div>
  );
}

function JobFollow({ jobId }) {
  const [state, setState] = useState("em curso…");
  useEffect(() => {
    pollCotesJob(jobId, { timeoutMs: 900000 })
      .then((res) => setState(res.verified ? `concluída — VERIFICADA, ${res.analysis?.inconsistencies?.length || 0} incoerência(s)` : `concluída — não verificada (${res.analysis?.inconsistencies?.length || 0} incoerência(s))`))
      .catch((e) => setState(`erro: ${e.message}`));
  }, [jobId]);
  return <div data-testid="assistant-job-state">Análise {state}</div>;
}

function EstimateCard({ e, r }) {
  const view = useDocumentViewer();
  const copy = async () => { try { await navigator.clipboard.writeText(`${window.location.origin}${r.share_url}`); toast.success("Link copiado"); } catch { toast.info(`${window.location.origin}${r.share_url}`); } };
  return (
    <div className="mt-1 grid gap-1.5" data-testid="assistant-estimate-card">
      <div className="grid grid-cols-3 gap-1 text-center">
        <div className="rounded-sm bg-emerald-500/10 border border-emerald-500/30 py-1.5"><div className="text-[10px] uppercase tracking-wide">Preço baixo</div><b className="text-sm" data-testid="assistant-estimate-low">{eur(e.low_estimate)}</b></div>
        <div className="rounded-sm bg-amber-500/10 border border-amber-500/30 py-1.5"><div className="text-[10px] uppercase tracking-wide">Central</div><b className="text-sm">{eur(e.central_estimate)}</b></div>
        <div className="rounded-sm bg-orange-500/10 border border-orange-500/30 py-1.5"><div className="text-[10px] uppercase tracking-wide">Preço alto</div><b className="text-sm" data-testid="assistant-estimate-high">{eur(e.high_estimate)}</b></div>
      </div>
      <div>Amplitude {e.range_percentage} % · {e.finish_level} · source : {e.price_source} ({e.price_date}, {e.reference_region}) · confiança {Math.round((e.confidence || 0) * 100)} %</div>
      {e.included_items?.length > 0 && <div>Incluído: {e.included_items.join(", ")}</div>}
      {e.excluded_items?.length > 0 && <div>Excluído: {e.excluded_items.join(", ")}</div>}
      <p className="italic text-muted-foreground border-l-2 border-orange-400 pl-2" data-testid="assistant-estimate-notice">{e.mandatory_notice}</p>
      {r?.share_url && (
        <div className="flex flex-wrap gap-2 pt-1">
          <button className="inline-flex items-center gap-1 px-2 py-1 rounded-sm border bg-background hover:bg-muted transition-colors" onClick={() => view(r.pdf, "construpilot-estimation.pdf", "Estimativa")} data-testid="assistant-estimate-pdf-btn"><FileDown className="h-3 w-3" /> Abrir o PDF</button>
          <button className="inline-flex items-center gap-1 px-2 py-1 rounded-sm border bg-background hover:bg-muted transition-colors" onClick={copy} data-testid="assistant-estimate-share-btn"><Link2 className="h-3 w-3" /> Copiar a ligação para partilhar</button>
          <a className="underline self-center" href={r.share_url} target="_blank" rel="noreferrer" data-testid="assistant-estimate-share-link">Abrir a página partilhada</a>
        </div>
      )}
    </div>
  );
}

export function ActionCard({ a }) {
  const quoteText = useQuoteCopy();
  const view = useDocumentViewer();
  const instance = useId().replace(/:/g, "");
  const isQuote = ["create_quote_draft", "update_quote_draft", "read_quote_draft"].includes(a.tool);
  const r = a.result || {};
  const dl = () => view(r.download, "rapport-construpilot.pdf", TOOL_LABEL[a.tool] || a.tool);
  return (
    <div className={`text-[11px] min-w-0 max-w-full rounded-sm border px-2 py-1.5 ${r.ok === false ? "border-red-300 bg-red-50 dark:bg-red-950/30" : "border-sky-300 bg-sky-50 dark:bg-sky-950/30"}`} data-testid={`assistant-action-${a.tool}${isQuote || r.artifact ? `-${instance}` : ""}`} data-tool={a.tool}>
      <b>{isQuote ? quoteText(a.tool === "read_quote_draft" ? "read" : a.tool === "update_quote_draft" ? "updated" : "quote") : a.tool === "save_user_preference" && r.preference && !r.preference.active ? "Preferência proposta" : TOOL_LABEL[a.tool] || a.tool}</b>{r.preview && " · pré-visualização"}{r.error && ` · ${r.error}`}
      {a.tool === "define_analysis_scope" && r.scope && (
        <div>incluídos: {r.scope.include.join(", ") || "—"} · excluídos: {r.scope.exclude.join(", ") || "—"} · controlos: {r.scope.checks.join(", ") || "—"} · sortie : {r.scope.output}</div>
      )}
      {isQuote && r.draft && a.tool !== "read_quote_draft" && <QuoteDraftCard result={r} />}
      {r.tracking_url && ["supervise_platform", "get_supervision_result"].includes(a.tool) && <div className="mt-2 space-y-1"><p>{r.status === "done" ? "Tratamento concluído; consulte os pontos que faltam verificar." : r.status === "error" ? "Tratamento interrompido; consulte os resultados parciais." : "O piloto trabalha em segundo plano. O resultado ainda não está validado."}</p><Link to={r.tracking_url} className="underline font-semibold">Acompanhar o controlo e as suas correções</Link></div>}
      {a.tool === "run_platform_calculator" && r.ok && <div className="mt-2 space-y-1">{r.results?.map((row, index) => <p key={index}>{row.label} : <strong>{row.value} {row.unit}</strong></p>)}<p className="text-muted-foreground">Provenance : {r.source}. As medições de partida continuam por confirmar.</p></div>}
      {r.artifact && <ArtifactCard artifact={r.artifact} />}
      {a.tool === "save_user_preference" && r.preference && <div>{r.preference.active ? "Ativa" : "Proposta, inativa"} · [{r.preference.scope}] {r.preference.category} = {r.preference.value} · <a className="underline" href="/preferences">Gerir a memória</a></div>}
      {["create_work_draft", "update_work_draft"].includes(a.tool) && r.draft && <WorkDraftCard initial={r.draft} />}
      {a.tool === "inspect_document_region" && r.ok && <div>{r.filename} · page {r.page} · zone agrandie<br />{r.note}</div>}
      {a.tool === "calculate" && r.ok && <div>{r.expression} = {r.result} {r.unit}<br />Origem: {r.source}</div>}
      {a.tool === "read_document" && r.ok && <div>{r.filename} · páginas {r.pages.map(p => p.page).join(", ")} / {r.total_pages}{r.next_page && " · outras páginas continuam disponíveis"}</div>}
      {a.tool === "estimate_budget_range" && r.estimate && <EstimateCard e={r.estimate} r={r} />}
      {a.tool === "compare_documents" && r.comparison && <CompareCard r={r} />}
      {a.tool === "fetch_verified_source" && <VerifiedSourceCard r={r} />}
      {a.tool === "search_product_sources" && <ProductSearchCard r={r} />}
      {a.tool === "compare_technical_options" && r.options && <OptionsCompareCard r={r} />}
      {a.tool === "check_dimension_chain" && r.calculation && <div data-testid="assistant-chain-card">{r.calculation.formula} · estado: {r.calculation.state}{r.findings?.length > 0 && ` · ${r.findings.length} ponto(s) a esclarecer`}</div>}
      {a.tool === "compare_dimension_values" && r.calculation && <div data-testid="assistant-compare-card">{r.calculation.formula} · {r.calculation.reason}</div>}
      {a.tool === "read_rebar_schedule" && !r.error && <RebarCard r={r} />}
      {a.tool === "draw_section_schema" && r.pdf_artifact && <ArtifactCard artifact={r.pdf_artifact} />}
      {a.tool === "update_project_state" && r.ok && <div data-testid="assistant-state-card">{r.op === "remove" ? "Entrada removida" : r.op === "update" ? "Entrada corrigida" : "Entrada adicionada"} · {r.section} · revisão {r.revision}</div>}
      {a.tool === "compute_concrete_volumes" && r.lines && <div data-testid="assistant-volumes-card">{r.lines.map((l, i) => <div key={i}>{l.element} : {l.net != null ? `${l.net} ${l.unit}` : "indeterminado"} · {l.state}</div>)}{r.total_m3 != null && <div><b>Total {r.total_m3} m³</b></div>}</div>}
      {a.tool === "calculate_quantities" && r.lines && <div data-testid="assistant-qty-card">{r.lines.map((l, i) => <div key={i}>{l.element} : {l.formula} · {l.state}{l.missing?.length ? ` · manque ${l.missing.join(", ")}` : ""}</div>)}</div>}
      {r.download && <button className="underline ml-1" onClick={dl} data-testid="assistant-download-btn"><FileDown className="inline h-3 w-3" /> Abrir / transferir</button>}
      {a.tool === "analyze_plan" && r.job_id && <JobFollow jobId={r.job_id} />}
    </div>
  );
}
