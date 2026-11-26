import { useEffect, useRef } from "react";
import { Link, useLocation } from "react-router-dom";
import { Route as RouteIcon, ExternalLink, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useI18n } from "@/context/I18nContext";
import { APP_FAMILIES, familyLabel } from "@/components/workspace/families";
import { comProcesso } from "@/lib/processoAtivo";
import { errorText } from "@/lib/errorText";

// Percurso do processo através das apps: cada trabalho aberto noutra app (Ateliê,
// BIM, medições, orçamento, estudos, PIC…) aparece aqui e reabre-se no mesmo processo.
const data = (iso) => { try { return new Date(iso).toLocaleString("pt-PT", { dateStyle: "short", timeStyle: "short" }); } catch { return ""; } };

export function PercursoApps({ c, chantierId, onChanged }) {
  const { lang } = useI18n();
  const { hash } = useLocation();
  const ref = useRef(null);
  const passos = Array.isArray(c?.percurso) ? c.percurso : [];

  useEffect(() => {
    if (hash === "#percurso") ref.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [hash, c]);

  const remover = async (passoId) => {
    try { await api.delete(`/chantiers/${chantierId}/percurso/${passoId}`); onChanged?.(); }
    catch (e) { toast.error(errorText(e, "Não foi possível retirar este passo.")); }
  };

  return <section ref={ref} id="percurso" className="surface p-4 scroll-mt-24" data-testid="chantier-percurso">
    <div className="flex items-center gap-2 mb-1">
      <RouteIcon className="h-4 w-4 text-primary" />
      <h2 className="text-sm font-semibold">Percurso entre apps</h2>
      <span className="text-xs text-muted-foreground">({passos.length})</span>
    </div>
    <p className="text-xs text-muted-foreground mb-3">
      Abra qualquer app a partir daqui: o processo acompanha o trabalho em todas as apps e cada resultado fica ligado a esta obra.
    </p>
    <div className="flex flex-wrap gap-2 mb-3" data-testid="chantier-percurso-apps">
      {APP_FAMILIES.filter(f => f.group === "chantiers" || f.group === "billing").map(f => (
        <Link key={f.id} to={comProcesso(f.to, chantierId)} className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1.5 text-xs hover:border-primary/60"
          data-testid={`chantier-percurso-abrir-${f.id}`}>
          <f.icon className="h-3.5 w-3.5 text-primary" />{familyLabel(f, lang)}
        </Link>))}
      <Link to={comProcesso("/assistant", chantierId)} className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1.5 text-xs hover:border-primary/60">Assistente BTP</Link>
    </div>
    {passos.length === 0
      ? <p className="text-xs text-muted-foreground">Ainda nenhum trabalho registado. Abra uma app acima: o que fizer lá fica ligado a este processo.</p>
      : <ol className="flex flex-col divide-y divide-border">
        {passos.map(p => <li key={p.passo_id} className="flex items-center gap-3 py-2" data-testid={`chantier-percurso-${p.passo_id}`}>
          <span className="h-2 w-2 rounded-full bg-primary shrink-0" aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium truncate">{p.app || p.rota}{p.titulo ? <span className="text-muted-foreground font-normal"> · {p.titulo}</span> : null}</p>
            <p className="text-[11px] text-muted-foreground truncate">{data(p.atualizado_em)}{p.resumo ? ` · ${p.resumo}` : ""}</p>
          </div>
          <Link to={p.url} className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline" data-testid={`chantier-percurso-reabrir-${p.passo_id}`}>
            Reabrir <ExternalLink className="h-3 w-3" />
          </Link>
          <button type="button" onClick={() => remover(p.passo_id)} title="Retirar do percurso" className="rounded p-1 text-muted-foreground hover:text-destructive">
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </li>)}
      </ol>}
  </section>;
}
