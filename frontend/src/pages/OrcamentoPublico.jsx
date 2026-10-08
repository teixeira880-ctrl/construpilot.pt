/**
 * Portal público do orçamento (Fase D).
 *
 * Rota: /orcamento-publico/:token  (fora de ProtectedRoute)
 *
 * Mostra o orçamento formatado sem exigir conta ConstruPilot. Inclui:
 *   - Dados do orçamento (items, totais, IVA PT)
 *   - Botão "Descarregar PDF"
 *   - Botão "Copiar ligação" (complementar — decisão 4a)
 *   - Call-to-action viral no rodapé
 */
import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import axios from "axios";
import {
  CheckCircle2, Download, Copy, Clock, Sparkles, ArrowRight,
  AlertTriangle,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { BotaoWhatsApp } from "@/components/btp/BotaoWhatsApp";
import { API } from "@/lib/api";

const fmtEUR = (v) =>
  Number(v || 0).toLocaleString("pt-PT", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }) + " €";

const fmtNumero = (v) => {
  const n = Number(v || 0);
  if (Math.abs(n - Math.round(n)) < 1e-9) return String(Math.round(n));
  return n.toLocaleString("pt-PT", { maximumFractionDigits: 2 });
};

export default function OrcamentoPublico() {
  const { token } = useParams();
  const [estado, setEstado] = useState({ loading: true, erro: null, dados: null });

  useEffect(() => {
    let cancelado = false;
    async function carregar() {
      try {
        const { data } = await axios.get(`${API}/public/orcamentos/${token}`);
        if (!cancelado) setEstado({ loading: false, erro: null, dados: data });
      } catch (e) {
        if (cancelado) return;
        const code = e?.response?.status;
        let mensagem = "Não foi possível carregar o orçamento.";
        if (code === 404) mensagem = "Ligação inválida ou não encontrada.";
        if (code === 410) mensagem = "Esta ligação expirou. Peça uma nova ao profissional.";
        if (code === 429) mensagem = "Demasiados pedidos — aguarde um momento.";
        setEstado({ loading: false, erro: mensagem, dados: null });
      }
    }
    carregar();
    return () => { cancelado = true; };
  }, [token]);

  const copiarLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      toast.success("Ligação copiada!");
    } catch {
      toast.error("Não foi possível copiar.");
    }
  };

  if (estado.loading) {
    return (
      <div className="min-h-screen grid place-items-center bg-slate-50 dark:bg-slate-950">
        <div className="text-center space-y-3" data-testid="orc-publico-loading">
          <div className="h-10 w-10 mx-auto border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-muted-foreground">A carregar o orçamento…</p>
        </div>
      </div>
    );
  }

  if (estado.erro) {
    return (
      <div className="min-h-screen grid place-items-center bg-slate-50 dark:bg-slate-950 p-6">
        <div className="max-w-md w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-8 text-center space-y-4"
             data-testid="orc-publico-erro">
          <AlertTriangle className="h-10 w-10 mx-auto text-amber-500" />
          <h1 className="text-xl font-bold">Ligação não disponível</h1>
          <p className="text-sm text-muted-foreground">{estado.erro}</p>
          <Link to="/">
            <Button variant="outline" className="rounded-sm">
              Ir para construpilot.pt
            </Button>
          </Link>
        </div>
      </div>
    );
  }

  const d = estado.dados;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-orange-50/40 dark:from-slate-950 dark:via-slate-900 dark:to-slate-950">
      {/* Barra superior minimalista com branding */}
      <header className="border-b border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/80 backdrop-blur">
        <div className="max-w-3xl mx-auto px-5 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold text-orange-600">ConstruPilot</span>
            <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
              · Portal cliente
            </span>
          </div>
          {d?.expires_at_iso && (
            <span className="text-[11px] text-muted-foreground flex items-center gap-1"
                  data-testid="orc-publico-expira">
              <Clock className="h-3 w-3" />
              Expira em {new Date(d.expires_at_iso).toLocaleDateString("pt-PT")}
            </span>
          )}
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-5 py-10 space-y-6" data-testid="orc-publico-pagina">
        {/* Cabeçalho */}
        <section className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground">
                {d.empresa?.nome || "ConstruPilot"}
              </p>
              <h1 className="font-bold text-2xl sm:text-3xl mt-1" data-testid="orc-publico-titulo">
                {d.titulo}
              </h1>
              {d.cliente_nome && (
                <p className="text-sm text-muted-foreground mt-1">
                  Para: <strong>{d.cliente_nome}</strong>
                </p>
              )}
              <p className="text-[11px] font-mono text-muted-foreground mt-1">
                Ref · {d.numero}
              </p>
            </div>
            <div className="rounded-md bg-orange-500 text-white px-4 py-3 text-center shrink-0">
              <div className="text-[10px] uppercase tracking-widest opacity-90">Total c/ IVA</div>
              <div className="text-2xl font-bold mt-0.5" data-testid="orc-publico-total">
                {fmtEUR(d.total_eur)}
              </div>
            </div>
          </div>
        </section>

        {/* Items */}
        <section className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-6">
          <h2 className="font-bold text-base mb-3">Rubricas</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="orc-publico-items">
              <thead>
                <tr className="text-left border-b border-slate-200 dark:border-slate-800 text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="py-2 pr-2">Descrição</th>
                  <th className="py-2 px-2 text-right">Qtd</th>
                  <th className="py-2 px-2">Un.</th>
                  <th className="py-2 px-2 text-right">Preço unit.</th>
                  <th className="py-2 pl-2 text-right">Total</th>
                </tr>
              </thead>
              <tbody>
                {(d.items || []).map((it, i) => (
                  <tr key={i} className="border-b border-slate-100 dark:border-slate-800/60">
                    <td className="py-2 pr-2">{it.descricao}</td>
                    <td className="py-2 px-2 text-right">{fmtNumero(it.qtd)}</td>
                    <td className="py-2 px-2 text-muted-foreground">{it.unidade}</td>
                    <td className="py-2 px-2 text-right">{fmtEUR(it.preco_unit_eur)}</td>
                    <td className="py-2 pl-2 text-right font-medium">{fmtEUR(it.total_eur)}</td>
                  </tr>
                ))}
                {(!d.items || d.items.length === 0) && (
                  <tr><td colSpan={5} className="py-8 text-center text-muted-foreground text-xs">
                    Sem rubricas definidas.
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Totais */}
          <div className="mt-4 space-y-1 text-sm max-w-xs ml-auto">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Subtotal</span>
              <span>{fmtEUR(d.subtotal_eur)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">IVA ({Number(d.iva_pct || 23).toFixed(0)}%)</span>
              <span>{fmtEUR(d.iva_eur)}</span>
            </div>
            <div className="flex justify-between pt-1 border-t border-slate-200 dark:border-slate-800 font-bold text-orange-600">
              <span>Total</span>
              <span>{fmtEUR(d.total_eur)}</span>
            </div>
          </div>
        </section>

        {/* Acções */}
        <section className="flex flex-wrap gap-2 justify-end" data-testid="orc-publico-acoes">
          <Button
            variant="outline"
            className="rounded-sm gap-2"
            onClick={copiarLink}
            data-testid="orc-publico-copiar"
          >
            <Copy className="h-4 w-4" /> Copiar ligação
          </Button>
          <BotaoWhatsApp
            url={typeof window !== "undefined" ? window.location.href : ""}
            mensagem={`Orçamento ${d.numero || ""} — ConstruPilot`}
            variant="outline"
            testid="orc-publico-whatsapp"
          />
          <a
            href={`${API}/public/orcamentos/${token}/pdf`}
            target="_blank"
            rel="noopener noreferrer"
            data-testid="orc-publico-pdf-link"
          >
            <Button className="rounded-sm gap-2 bg-orange-600 hover:bg-orange-700">
              <Download className="h-4 w-4" /> Descarregar PDF
            </Button>
          </a>
        </section>

        {/* Nota de confiança */}
        <section className="bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-900/50 rounded-xl p-4 flex items-start gap-3">
          <CheckCircle2 className="h-5 w-5 text-emerald-600 mt-0.5 shrink-0" />
          <p className="text-sm text-emerald-900 dark:text-emerald-200">
            Este orçamento foi preparado especialmente para si. Para qualquer
            dúvida ou alteração, contacte directamente o profissional que o
            enviou.
          </p>
        </section>

        {/* CTA viral — rodapé */}
        <footer className="pt-10 pb-6 text-center" data-testid="orc-publico-cta-viral">
          <p className="text-xs text-muted-foreground mb-3 flex items-center justify-center gap-1">
            <Sparkles className="h-3 w-3 text-orange-500" />
            Este orçamento foi criado com <strong>ConstruPilot</strong>
          </p>
          <p className="text-sm">
            IA para orçamentos de obras —&nbsp;
            <Link
              to="/"
              className="text-orange-600 font-semibold inline-flex items-center gap-1 hover:underline"
            >
              Experimente grátis <ArrowRight className="h-3 w-3" />
            </Link>
          </p>
        </footer>
      </main>
    </div>
  );
}
