import { useId } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, FilePenLine, CheckCircle2, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { eur2 as eur } from "@/lib/api";
import { useQuoteCopy } from "./quoteCopy";

export const QuoteDraftCard = ({ result }) => {
  const text = useQuoteCopy();
  const instance = useId().replace(/:/g, "");
  const d = result.draft;
  const id = name => `assistant-quote-${name}-${d.doc_id || d.draft_id}-${instance}`;
  const saved = result.saved && /^doc_[a-zA-Z0-9_-]+$/.test(result.doc_id || "");
  return <div className="grid gap-3 pt-2 text-sm min-w-0" data-testid={id("card")} data-doc-id={result.doc_id || ""}>
    <div className="flex flex-wrap items-center gap-2"><CheckCircle2 size={16} className="text-primary" /><strong data-testid={id("state")}>{text(saved ? "saved" : "legacy")}</strong>{saved && <span className="text-xs text-muted-foreground" data-testid={id("unsent")}>{text("noSend")}</span>}</div>
    <div className="grid gap-1"><p className="font-semibold break-words" data-testid={id("title")}>{d.title}</p><p className="text-xs text-muted-foreground break-words" data-testid={id("client")}>{d.client_name || text("emptyClient")}</p></div>
    <div className="flex flex-wrap gap-x-5 gap-y-2 num text-xs">{[["ht", "HT", d.total_ht], ["vat", "TVA", d.total_tva], ["ttc", "TTC", d.total_ttc]].map(([key, label, value]) => <span key={key} data-testid={id(`total-${key}`)}>{label} <strong>{eur(value)}</strong></span>)}</div>
    {(d.estimated_lines > 0 || d.incomplete_lines > 0 || d.vat_assumed) && <div className="border-l-2 border-amber-500 pl-3 text-xs grid gap-1 text-amber-700 dark:text-amber-400" data-testid={id("review")}>
      {d.estimated_lines > 0 && <p data-testid={id("estimates")}>{text("estimates")} · {d.estimated_lines}</p>}{d.incomplete_lines > 0 && <p data-testid={id("missing")}>{text("missing")}</p>}{d.vat_assumed && <p data-testid={id("vat-warning")}>{text("vat")}</p>}
    </div>}
    {saved && d.estimated_lines > 0 && <Link to="/bibliotheque" data-testid={id("learned-cta")}
      className="flex items-center gap-2 rounded-sm border border-amber-400/60 bg-amber-50 dark:bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-300 hover:border-amber-500 transition-colors">
      <Sparkles size={14} className="shrink-0" />
      <span>{d.estimated_lines} prix moyen{d.estimated_lines > 1 ? "s" : ""} marché appris — validez-les pour fiabiliser vos prochains devis</span>
      <ArrowRight size={14} className="shrink-0 ml-auto" />
    </Link>}
    {saved && <div className="flex flex-wrap gap-2"><Button asChild size="sm" className="h-auto min-h-9 max-w-full whitespace-normal py-2"><Link to={`/devis-editeur/${result.doc_id}`} data-testid={id("open")}><FilePenLine size={15} />{text("edit")}</Link></Button><Button asChild variant="outline" size="sm" className="h-auto min-h-9 max-w-full whitespace-normal py-2"><Link to={`/devis?highlight=${result.doc_id}`} data-testid={id("tracking")}><ArrowRight size={15} />{text("tracking")}</Link></Button></div>}
  </div>;
};