import { ArrowRight, ChevronDown, ClipboardCheck, FileDown, FileText, Loader2, Ruler, Settings2, Sparkles } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import "./PlanWorkspace.css";

const MODES = {
  complete: { label: "Análise completa · esta página", description: "Estrutura, divisões, medições e estimativa. Verifique depois os contornos e as hipóteses." },
  reading: { label: "Leitura das cotas e divisões · esta página", description: "Identificação dos textos, divisões e vãos, possível antes da calibração. Nenhuma medição validada nesta etapa." },
  structure_all: { label: "Estrutura · todas as páginas", description: "Deteção das paredes, pilares, vigas e lajes no documento. As divisões e a orçamentação continuam a ser tratadas por página." },
};

function ActionMenu({ label, icon: Icon, actions, disabled }) {
  return <DropdownMenu>
    <DropdownMenuTrigger asChild>
      <button type="button" className="plan-menu-button" disabled={disabled}>
        <Icon size={16} aria-hidden="true" /> {label} <ChevronDown size={14} aria-hidden="true" />
      </button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" className="min-w-56 max-w-[calc(100vw-2rem)]">
      {actions.filter(Boolean).map((action) => action.separator
        ? <DropdownMenuSeparator key={action.id} />
        : <DropdownMenuItem key={action.id} onSelect={action.run} disabled={action.disabled}
            data-testid={action.id} className={action.danger ? "text-destructive focus:text-destructive" : ""}>
            {action.label}
          </DropdownMenuItem>)}
    </DropdownMenuContent>
  </DropdownMenu>;
}

export default function PlanWorkflowHeader({ filename, pageIndex, pageCount, calibration, busy, mode, onModeChange,
  planKind, onPlanKindChange, onAnalyze, progress, hasRecap, onCalibrate, onReview, onEstimate,
  documentActions, exportActions, studyActions, children }) {
  const selectedMode = MODES[mode] || MODES.complete;
  const stage = busy ? 1 : !calibration ? 0 : hasRecap ? 2 : 1;
  const steps = [
    { title: "Escala", detail: calibration ? "Calibração guardada" : "Dimensão de referência", icon: Ruler, run: onCalibrate },
    { title: "Analyse", detail: "Leitura e quantidades", icon: Sparkles, run: () => document.getElementById("plan-analysis-mode")?.focus() },
    { title: "Controlo", detail: "Cotas e hipóteses", icon: ClipboardCheck, run: onReview },
    { title: "Chiffrage", detail: "Preços e orçamento", icon: FileText, run: onEstimate },
  ];
  return <header className="plan-workflow-header" data-testid="plan-workflow-header">
    <div className="plan-workflow-heading">
      <div className="min-w-0">
        <p className="plan-eyebrow">ESPAÇO DE TRABALHO · CONSTRUPILOT</p>
        <h1>Plantas e medições<span className="plan-title-dot" aria-hidden="true">.</span></h1>
        <p className="plan-document-name" data-testid="plan-filename" title={filename}>{filename}</p>
      </div>
      <div className="plan-document-tools">
        {children}
        <ActionMenu label="Document" icon={FileText} actions={documentActions} disabled={busy} />
        <ActionMenu label="Exporter" icon={FileDown} actions={exportActions} disabled={busy} />
        <ActionMenu label="Outils" icon={Settings2} actions={studyActions} disabled={busy} />
      </div>
    </div>
    <nav className="plan-workflow-steps" aria-label="Etapas da medição">
      {steps.map((step, index) => <button type="button" key={step.title} onClick={step.run} disabled={busy}
        aria-current={index === stage ? "step" : undefined} className="plan-workflow-step">
        <span className="plan-step-number">{String(index + 1).padStart(2, "0")}</span>
        <span><strong>{step.title}</strong><small>{step.detail}</small></span>
        <step.icon size={17} aria-hidden="true" />
      </button>)}
    </nav>
    <div className="plan-analysis-controls" data-testid="plan-actions" aria-busy={busy}>
      <div className="plan-analysis-context">
        <span className="plan-page-chip">Page {pageIndex + 1} / {pageCount}</span>
        <span className={calibration ? "plan-scale-status" : "plan-scale-status is-pending"} data-testid="calib-badge">
          <span aria-hidden="true" />{calibration ? "Escala indicada" : "Escala a indicar"}
        </span>
      </div>
      <div className="plan-analysis-fields">
        <label>Tipo de planta
          <select value={planKind} onChange={(e) => onPlanKindChange(e.target.value)} disabled={busy || mode !== "complete"} data-testid="analyze-kind-toggle">
            <option value="auto">Deteção automática</option><option value="gros_oeuvre">Obra grossa</option><option value="maison">Maison</option>
          </select>
        </label>
        <label className="plan-mode-field">Analyse
          <select id="plan-analysis-mode" value={mode} onChange={(e) => onModeChange(e.target.value)} disabled={busy} aria-describedby="plan-analysis-description">
            {Object.entries(MODES).filter(([key]) => key !== "structure_all" || pageCount > 1).map(([key, value]) => <option key={key} value={key}>{value.label}</option>)}
          </select>
        </label>
        <button type="button" className="plan-primary-action" onClick={onAnalyze} disabled={busy} data-testid="plan-analyze-btn">
          {busy ? <Loader2 size={17} className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <Sparkles size={17} aria-hidden="true" />}
          {busy ? "Analyse en cours…" : "Analisar a planta"}
          {!busy && <ArrowRight size={16} aria-hidden="true" />}
        </button>
      </div>
      <p id="plan-analysis-description" className="plan-analysis-description">{selectedMode.description}</p>
      {busy && <p className="plan-analysis-progress" role="status" aria-live="polite">{progress || "A preparar a análise…"}</p>}
    </div>
  </header>;
}

export function PlanAnalysisResults({ recap, onClose, onReview, onQuote }) {
  const amount = recap.estimation_globale_eur ?? recap.estimation_beton_eur;
  const warnings = recap.warnings || [];
  return <section className="plan-analysis-results" data-testid="analysis-recap" aria-label="Resultados da análise">
    <div className="plan-results-heading">
      <div><p className="plan-eyebrow">RESULTADOS · ESTA PÁGINA</p><h2>A sua medição ganha forma</h2></div>
      <span className="plan-review-badge">{warnings.length ? "Analyse partielle" : "A verificar na planta"}</span>
      <button type="button" onClick={onClose} className="plan-text-button" data-testid="recap-close">Masquer</button>
    </div>
    <div className="plan-results-grid">
      <div data-testid="recap-surface"><span>Área das divisões medidas</span><strong>{recap.surface_pieces_m2 == null ? "A medir" : `${recap.surface_pieces_m2.toLocaleString("fr-FR")} m²`}</strong><small data-testid="recap-rooms">{recap.rooms} divisão{recap.rooms > 1 ? "s" : ""} · contornos a controlar</small></div>
      <div data-testid="recap-beton"><span>Betão estimado</span><strong>{recap.beton_m3 == null ? "Indisponible" : `${recap.beton_m3.toLocaleString("fr-FR")} m³`}</strong><small>Espessuras e alturas a confirmar</small></div>
      <div data-testid="recap-estimation"><span>Budget indicatif</span><strong>{amount == null ? "Indisponible" : `${amount.toLocaleString("fr-FR")} €`}</strong><small>{recap.estimation_globale_eur != null ? "Remodelação · planta completa (média)" : "Estrutura · esta página"}</small></div>
    </div>
    <div className="plan-results-footnotes">
      <p data-testid="recap-structure">Estrutura identificada: {recap.walls} paredes · {recap.columns} poteaux · {recap.beams} poutres · {recap.floors} dalles</p>
      <p data-testid="recap-acier">Aço estimado por rácios: {recap.acier_kg == null ? "indisponible" : `${recap.acier_kg.toLocaleString("fr-FR")} kg`}</p>
    </div>
    {!!warnings.length && <div className="plan-results-warnings" role="status"><strong>Pontos a retomar</strong><ul>{warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></div>}
    <div className="plan-results-actions">
      <button type="button" onClick={onReview} className="plan-primary-action" data-testid="recap-see-rooms"><ClipboardCheck size={16} aria-hidden="true" /> Controlar os resultados</button>
      <button type="button" onClick={onQuote} className="plan-menu-button" data-testid="recap-to-quote">Preparar o orçamento <ArrowRight size={16} aria-hidden="true" /></button>
    </div>
  </section>;
}
