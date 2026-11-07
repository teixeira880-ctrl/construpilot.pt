import { useNavigate } from "react-router-dom";
import { Check } from "lucide-react";

// Lote 109 PT — fluxo do projeto: Plantas → Medição → Orçamento → Envio e assinatura → Obra e faturação.
// Lê só dados que a página já tem (c), não faz pedidos à API. Cada passo leva à ação certa.
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

export function ProjectFlow({ c, chantierId, onTab }) {
  const nav = useNavigate();
  if (!c) return null;
  const ctx = `?chantier=${chantierId}`;
  const docs = Array.isArray(c.documents) ? c.documents : [];
  const plans = Array.isArray(c.plans) ? c.plans : [];
  const jobs = Array.isArray(c.plans_pro) ? c.plans_pro : [];
  const quotes = docs.filter(d => d.doc_type === "quote");
  const invoices = docs.filter(d => d.doc_type !== "quote");
  const sent = quotes.filter(d => ["sent", "signed", "refused"].includes(d.status));
  const signed = quotes.filter(d => d.status === "signed");
  const review = jobs.filter(j => ["needs_review", "partial"].includes(j.status)).length;
  const files = plans.length || jobs.length;
  const measured = (jobs.some(j => j.status === "done") || quotes.length > 0) && review === 0;

  const steps = [
    { key: "plans", title: "Plantas", done: files > 0,
      sub: files > 0 ? plural(files, "ficheiro", "ficheiros") : "Importar PDF, DWG ou DXF",
      go: () => nav(`/plan${ctx}`) },
    { key: "takeoff", title: "Medição", done: measured,
      sub: review ? plural(review, "ponto a verificar", "pontos a verificar") : measured ? "Quantidades prontas" : "Medir na planta",
      go: () => nav(jobs.length ? `/plans-pro${ctx}` : `/plan${ctx}`) },
    { key: "quote", title: "Orçamento", done: quotes.length > 0,
      sub: quotes.length ? plural(quotes.length, "orçamento", "orçamentos") : "Criar a partir das quantidades",
      go: () => nav(`/devis-editeur${ctx}`) },
    { key: "send", title: "Envio e assinatura", done: signed.length > 0,
      sub: signed.length ? "Assinado pelo cliente" : sent.length ? plural(sent.length, "enviado", "enviados") : "Enviar ao cliente",
      go: () => onTab?.("documents") },
    { key: "works", title: "Obra e faturação", done: invoices.length > 0,
      sub: invoices.length ? plural(invoices.length, "fatura", "faturas") : "Autos e faturas",
      go: () => onTab?.("documents") },
  ];
  const current = steps.findIndex(s => !s.done);

  return <nav className="cp2-flow" aria-label="Etapas do projeto" data-testid="chantier-flow">
    <ol>{steps.map((s, i) => {
      const state = s.done ? "done" : i === current ? "current" : "todo";
      const status = s.done ? "concluído" : i === current ? "etapa atual" : "por fazer";
      return <li key={s.key}>
        <button type="button" className="cp2-step" data-state={state} aria-current={i === current ? "step" : undefined}
          onClick={s.go} data-testid={`chantier-flow-${s.key}`}>
          <span className="cp2-dot" aria-hidden="true">{s.done ? <Check size={15} strokeWidth={3} /> : i + 1}</span>
          <span><b>{s.title}</b><small>{s.sub}<span className="sr-only"> — {status}</span></small></span>
        </button>
      </li>;
    })}</ol>
  </nav>;
}
