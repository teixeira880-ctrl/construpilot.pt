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
  supervise_platform: "Contrôle du dossier lancé", get_supervision_result: "État du contrôle",
  cancel_supervision: "Arrêt du contrôle demandé",
  list_platform_resources: "Documents du compte", list_platform_calculators: "Calculateurs disponibles", run_platform_calculator: "Calcul de matériaux",
  create_downloadable_file: "Fichier créé", read_generated_file: "Fichier relu",
  inspect_document_region: "Détail du document consulté", read_work_draft: "Brouillon relu", update_work_draft: "Brouillon révisé",
  read_document: "Pages consultées", calculate: "Calcul vérifié", create_work_draft: "Brouillon modifiable", search_own_history: "Vos échanges retrouvés",
  define_analysis_scope: "Périmètre d'analyse", analyze_plan: "Analyse approfondie lancée", get_plan_results: "Résultats du plan lus",
  generate_branded_pdf: "Rapport PDF", create_quote_draft: "Brouillon de devis", save_user_preference: "Préférence mémorisée",
  create_project_task: "Tâche créée", estimate_budget_range: "Estimation budgétaire indicative", compare_documents: "Comparaison de documents",
  search_product_sources: "Documentation produit recherchée", fetch_verified_source: "Source consultée", compare_technical_options: "Solutions comparées",
  check_dimension_chain: "Chaîne de cotes calculée", compare_dimension_values: "Cotes comparées", resolve_ambiguous_reading: "Lecture ambiguë examinée",
  classify_strokes: "Traits classés", dedupe_elements: "Éléments dédoublonnés", calculate_quantities: "Quantités calculées",
  read_rebar_schedule: "Nomenclature d'aciers lue", read_native_dimensions: "Cotes natives lues",
  compute_concrete_volumes: "Volumes de béton calculés", update_project_state: "État du dossier mis à jour", draw_section_schema: "Schéma de principe coté dessiné",
};

function RebarCard({ r }) {
  const ha = r.native?.ha_bars, mesh = r.native?.mesh, recap = r.native?.mesh_recap, el = r.sheet?.element, chk = r.sheet?.checks;
  return (
    <div data-testid="assistant-rebar-card">
      {r.requires_vision && <div>Texte vectorisé : relancez avec lecture visuelle (appel facturé).</div>}
      {ha && <div>Aciers HA : {ha.count} repères · masse théorique {ha.total_mass_kg} kg · {ha.inconsistencies?.length || 0} incohérence(s) arithmétique(s)
        {ha.comparison && ` · écart vs récap ${ha.comparison.difference_kg > 0 ? "+" : ""}${ha.comparison.difference_kg} kg`}</div>}
      {mesh && <div>Treillis : {mesh.count} panneaux · {mesh.rows_mass_kg} kg{recap?.mass_laid_kg != null && ` · masse posée ${recap.mass_laid_kg} kg`}</div>}
      {r.native?.partial && <div>Nomenclature marquée « partielle » sur la feuille.</div>}
      {el && <div>Feuille {el.label || "?"} · Béton {el.concrete_m3 ?? "—"} m³ · Acier {el.steel_kg ?? "—"} kg · {chk?.inconsistencies?.length || 0} écart(s) Lg/Poids · lecture visuelle à vérifier</div>}
    </div>
  );
}

function JobFollow({ jobId }) {
  const [state, setState] = useState("en cours…");
  useEffect(() => {
    pollCotesJob(jobId, { timeoutMs: 900000 })
      .then((res) => setState(res.verified ? `terminée — VÉRIFIÉE, ${res.analysis?.inconsistencies?.length || 0} incohérence(s)` : `terminée — non vérifiée (${res.analysis?.inconsistencies?.length || 0} incohérence(s))`))
      .catch((e) => setState(`erreur : ${e.message}`));
  }, [jobId]);
  return <div data-testid="assistant-job-state">Analyse {state}</div>;
}

function EstimateCard({ e, r }) {
  const view = useDocumentViewer();
  const copy = async () => { try { await navigator.clipboard.writeText(`${window.location.origin}${r.share_url}`); toast.success("Lien copié"); } catch { toast.info(`${window.location.origin}${r.share_url}`); } };
  return (
    <div className="mt-1 grid gap-1.5" data-testid="assistant-estimate-card">
      <div className="grid grid-cols-3 gap-1 text-center">
        <div className="rounded-sm bg-emerald-500/10 border border-emerald-500/30 py-1.5"><div className="text-[10px] uppercase tracking-wide">Prix bas</div><b className="text-sm" data-testid="assistant-estimate-low">{eur(e.low_estimate)}</b></div>
        <div className="rounded-sm bg-amber-500/10 border border-amber-500/30 py-1.5"><div className="text-[10px] uppercase tracking-wide">Central</div><b className="text-sm">{eur(e.central_estimate)}</b></div>
        <div className="rounded-sm bg-orange-500/10 border border-orange-500/30 py-1.5"><div className="text-[10px] uppercase tracking-wide">Prix haut</div><b className="text-sm" data-testid="assistant-estimate-high">{eur(e.high_estimate)}</b></div>
      </div>
      <div>Amplitude {e.range_percentage} % · {e.finish_level} · source : {e.price_source} ({e.price_date}, {e.reference_region}) · confiance {Math.round((e.confidence || 0) * 100)} %</div>
      {e.included_items?.length > 0 && <div>Inclus : {e.included_items.join(", ")}</div>}
      {e.excluded_items?.length > 0 && <div>Exclus : {e.excluded_items.join(", ")}</div>}
      <p className="italic text-muted-foreground border-l-2 border-orange-400 pl-2" data-testid="assistant-estimate-notice">{e.mandatory_notice}</p>
      {r?.share_url && (
        <div className="flex flex-wrap gap-2 pt-1">
          <button className="inline-flex items-center gap-1 px-2 py-1 rounded-sm border bg-background hover:bg-muted transition-colors" onClick={() => view(r.pdf, "construpilot-estimation.pdf", "Estimation")} data-testid="assistant-estimate-pdf-btn"><FileDown className="h-3 w-3" /> Ouvrir le PDF</button>
          <button className="inline-flex items-center gap-1 px-2 py-1 rounded-sm border bg-background hover:bg-muted transition-colors" onClick={copy} data-testid="assistant-estimate-share-btn"><Link2 className="h-3 w-3" /> Copier le lien à partager</button>
          <a className="underline self-center" href={r.share_url} target="_blank" rel="noreferrer" data-testid="assistant-estimate-share-link">Ouvrir la page partagée</a>
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
      <b>{isQuote ? quoteText(a.tool === "read_quote_draft" ? "read" : a.tool === "update_quote_draft" ? "updated" : "quote") : a.tool === "save_user_preference" && r.preference && !r.preference.active ? "Préférence proposée" : TOOL_LABEL[a.tool] || a.tool}</b>{r.preview && " · prévisualisation"}{r.error && ` · ${r.error}`}
      {a.tool === "define_analysis_scope" && r.scope && (
        <div>inclus : {r.scope.include.join(", ") || "—"} · exclus : {r.scope.exclude.join(", ") || "—"} · contrôles : {r.scope.checks.join(", ") || "—"} · sortie : {r.scope.output}</div>
      )}
      {isQuote && r.draft && a.tool !== "read_quote_draft" && <QuoteDraftCard result={r} />}
      {r.tracking_url && ["supervise_platform", "get_supervision_result"].includes(a.tool) && <div className="mt-2 space-y-1"><p>{r.status === "done" ? "Traitement terminé ; consultez les points restant à vérifier." : r.status === "error" ? "Traitement interrompu ; consultez les résultats partiels." : "Le pilote travaille en arrière-plan. Le résultat n’est pas encore validé."}</p><Link to={r.tracking_url} className="underline font-semibold">Suivre le contrôle et ses corrections</Link></div>}
      {a.tool === "run_platform_calculator" && r.ok && <div className="mt-2 space-y-1">{r.results?.map((row, index) => <p key={index}>{row.label} : <strong>{row.value} {row.unit}</strong></p>)}<p className="text-muted-foreground">Provenance : {r.source}. Les mesures de départ restent à confirmer.</p></div>}
      {r.artifact && <ArtifactCard artifact={r.artifact} />}
      {a.tool === "save_user_preference" && r.preference && <div>{r.preference.active ? "Active" : "Proposée, inactive"} · [{r.preference.scope}] {r.preference.category} = {r.preference.value} · <a className="underline" href="/preferences">Gérer la mémoire</a></div>}
      {["create_work_draft", "update_work_draft"].includes(a.tool) && r.draft && <WorkDraftCard initial={r.draft} />}
      {a.tool === "inspect_document_region" && r.ok && <div>{r.filename} · page {r.page} · zone agrandie<br />{r.note}</div>}
      {a.tool === "calculate" && r.ok && <div>{r.expression} = {r.result} {r.unit}<br />Origine : {r.source}</div>}
      {a.tool === "read_document" && r.ok && <div>{r.filename} · pages {r.pages.map(p => p.page).join(", ")} / {r.total_pages}{r.next_page && " · d'autres pages restent disponibles"}</div>}
      {a.tool === "estimate_budget_range" && r.estimate && <EstimateCard e={r.estimate} r={r} />}
      {a.tool === "compare_documents" && r.comparison && <CompareCard r={r} />}
      {a.tool === "fetch_verified_source" && <VerifiedSourceCard r={r} />}
      {a.tool === "search_product_sources" && <ProductSearchCard r={r} />}
      {a.tool === "compare_technical_options" && r.options && <OptionsCompareCard r={r} />}
      {a.tool === "check_dimension_chain" && r.calculation && <div data-testid="assistant-chain-card">{r.calculation.formula} · état : {r.calculation.state}{r.findings?.length > 0 && ` · ${r.findings.length} point(s) à éclaircir`}</div>}
      {a.tool === "compare_dimension_values" && r.calculation && <div data-testid="assistant-compare-card">{r.calculation.formula} · {r.calculation.reason}</div>}
      {a.tool === "read_rebar_schedule" && !r.error && <RebarCard r={r} />}
      {a.tool === "draw_section_schema" && r.pdf_artifact && <ArtifactCard artifact={r.pdf_artifact} />}
      {a.tool === "update_project_state" && r.ok && <div data-testid="assistant-state-card">{r.op === "remove" ? "Entrée retirée" : r.op === "update" ? "Entrée corrigée" : "Entrée ajoutée"} · {r.section} · révision {r.revision}</div>}
      {a.tool === "compute_concrete_volumes" && r.lines && <div data-testid="assistant-volumes-card">{r.lines.map((l, i) => <div key={i}>{l.element} : {l.net != null ? `${l.net} ${l.unit}` : "indéterminé"} · {l.state}</div>)}{r.total_m3 != null && <div><b>Total {r.total_m3} m³</b></div>}</div>}
      {a.tool === "calculate_quantities" && r.lines && <div data-testid="assistant-qty-card">{r.lines.map((l, i) => <div key={i}>{l.element} : {l.formula} · {l.state}{l.missing?.length ? ` · manque ${l.missing.join(", ")}` : ""}</div>)}</div>}
      {r.download && <button className="underline ml-1" onClick={dl} data-testid="assistant-download-btn"><FileDown className="inline h-3 w-3" /> Ouvrir / télécharger</button>}
      {a.tool === "analyze_plan" && r.job_id && <JobFollow jobId={r.job_id} />}
    </div>
  );
}
