import { useState } from "react";
import { toast } from "sonner";
import { BadgeCheck, FileText, Phone, Mail, Star, CheckCircle2, XCircle, PenLine, HardHat, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api, API, eur2 } from "@/lib/api";
import { ProjectSiteTracking } from "@/components/ProjectSiteTracking";

const STATUS = { accepted: ["Aceite", "bg-emerald-500/15 text-emerald-700"], signed: ["Assinado", "bg-emerald-500/15 text-emerald-700"],
  refused: ["Recusado", "bg-red-500/10 text-red-600"], issued: ["Recebido", "bg-primary/10 text-primary"], sent: ["Recebido", "bg-primary/10 text-primary"] };

export const ProjectArtisanSection = ({ project, onChange }) => {
  const a = project?.artisan;
  const [busy, setBusy] = useState("");
  if (!a || (!a.assigned_pro && !a.quotes?.length)) return null;

  const act = async (doc, action) => {
    setBusy(doc.doc_id + action);
    try {
      const { data } = await api.post(`/projects/${project.project_id}/quotes/${doc.doc_id}/${action}`);
      toast.success(action === "accept" ? "Orçamento aceite — o profissional foi avisado" : "Orçamento recusado");
      onChange?.(data);
      if (action === "accept" && data.sign_url) window.open(data.sign_url, "_blank", "noopener");
    } catch (e) { toast.error(e?.response?.data?.detail || "Ação impossível"); } finally { setBusy(""); }
  };

  const pro = a.assigned_pro;
  return (
    <section className="surface rounded-xl p-6 grid gap-5" data-testid="project-artisan-section">
      <div className="flex items-center gap-2">
        <HardHat className="h-5 w-5 text-primary" />
        <h2 className="font-display text-base md:text-lg font-bold">Profissional e orçamento</h2>
        {a.accepted_quote && <Badge className="rounded-sm bg-emerald-500/15 text-emerald-700 hover:bg-emerald-500/15" data-testid="project-quote-accepted-badge">Orçamento aceite</Badge>}
      </div>

      {pro && (
        <div className="flex flex-wrap items-center gap-4 rounded-sm border border-border/60 bg-secondary/20 p-4" data-testid="project-assigned-pro">
          <div className="h-11 w-11 rounded-full bg-primary/15 grid place-items-center font-display font-bold text-primary">{(pro.company_name || "P").slice(0, 2).toUpperCase()}</div>
          <div className="min-w-0">
            <div className="font-semibold flex items-center gap-2">{pro.company_name}
              {pro.verified && <span className="inline-flex items-center gap-1 text-[11px] text-emerald-700 font-bold"><BadgeCheck className="h-3.5 w-3.5" /> Pro verificado</span>}
            </div>
            <div className="text-xs text-muted-foreground flex flex-wrap gap-3 mt-1">
              {pro.contact_name && <span>{pro.contact_name}</span>}
              {pro.city && <span>{pro.city}</span>}
              {pro.rating && <span className="inline-flex items-center gap-1"><Star className="h-3 w-3 text-amber-500" /> {pro.rating} ({pro.reviews_count})</span>}
            </div>
          </div>
          <div className="ml-auto flex flex-wrap gap-2 text-sm">
            {pro.phone && <a href={`tel:${pro.phone}`} className="inline-flex items-center gap-1.5 rounded-sm border border-border px-3 py-1.5 hover:bg-primary/5" data-testid="project-pro-phone"><Phone className="h-3.5 w-3.5" /> {pro.phone}</a>}
            {pro.email && <a href={`mailto:${pro.email}`} className="inline-flex items-center gap-1.5 rounded-sm border border-border px-3 py-1.5 hover:bg-primary/5" data-testid="project-pro-email"><Mail className="h-3.5 w-3.5" /> Escrever</a>}
            <a href={pro.profile_url} className="inline-flex items-center rounded-sm px-3 py-1.5 text-primary hover:underline" data-testid="project-pro-profile">Perfil →</a>
          </div>
        </div>
      )}

      {a.quotes?.length > 0 ? (
        <div className="grid gap-2" data-testid="project-quotes-list">
          {a.quotes.map((q) => {
            const [label, cls] = STATUS[q.accepted ? "accepted" : q.status] || ["Recebido", "bg-primary/10 text-primary"];
            return (
              <div key={q.doc_id} className="flex flex-wrap items-center gap-3 rounded-sm border border-border/60 p-3" data-testid={`project-quote-${q.doc_id}`}>
                <FileText className="h-4 w-4 text-primary shrink-0" />
                <div className="min-w-0">
                  <div className="font-medium truncate">{q.number ? `Orçamento ${q.number}` : "Orçamento"} — {q.title}</div>
                  <div className="text-xs text-muted-foreground">{q.lines_count} linhas · {q.issue_date ? new Date(q.issue_date).toLocaleDateString("pt-PT") : ""}</div>
                </div>
                <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${cls}`} data-testid={`project-quote-status-${q.doc_id}`}>{label}</span>
                <div className="ml-auto flex items-center gap-2">
                  <span className="num font-semibold" data-testid={`project-quote-total-${q.doc_id}`}>{eur2(q.total_ttc || 0)} c/ IVA</span>
                  <a href={`${API}${q.pdf_url.replace(/^\/api/, "")}`} target="_blank" rel="noreferrer" className="text-sm text-primary hover:underline" data-testid={`project-quote-pdf-${q.doc_id}`}>PDF</a>
                  {!q.accepted && !q.declined_at && (
                    <>
                      <Button size="sm" className="rounded-sm gap-1.5 h-8" disabled={!!busy} onClick={() => act(q, "accept")} data-testid={`project-quote-accept-${q.doc_id}`}>
                        {busy === q.doc_id + "accept" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />} Aceitar
                      </Button>
                      <Button size="sm" variant="outline" className="rounded-sm gap-1.5 h-8" disabled={!!busy} onClick={() => act(q, "decline")} data-testid={`project-quote-decline-${q.doc_id}`}>
                        <XCircle className="h-3.5 w-3.5" /> Recusar
                      </Button>
                    </>
                  )}
                  {q.accepted && !q.signed && q.sign_url && (
                    <a href={q.sign_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 rounded-sm bg-primary text-primary-foreground px-3 h-8 text-sm" data-testid={`project-quote-sign-${q.doc_id}`}><PenLine className="h-3.5 w-3.5" /> Assinar online</a>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground" data-testid="project-quotes-empty">O profissional está a preparar o seu orçamento: aparecerá aqui assim que for enviado.</p>
      )}
      <ProjectSiteTracking projectId={project.project_id} acceptedQuote={a.accepted_quote} />
    </section>
  );
};
