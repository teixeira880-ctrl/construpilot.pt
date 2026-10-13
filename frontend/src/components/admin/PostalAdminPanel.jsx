import { useState } from "react";
import { ShieldCheck, AlertTriangle, RefreshCw, Truck } from "lucide-react";
import { api } from "@/lib/api";
import { useI18n } from "@/context/I18nContext";
import { Button } from "@/components/ui/button";
import { usePostalCopy } from "@/components/radar/postalCopy";

const LABELS = {
  fr: { title: "Correio postal", check: "Verificar a ligação postal", pending: "A verificar…", good: "O Merci Facteur respondeu: os preços funcionam neste ambiente.", bad: "A ligação postal necessita de correção.", ips: "IPs autorizados na configuração", observed: "IP de saída observado", note: "A verificação de IP e o Merci Facteur podem usar saídas diferentes. O resultado do fornecedor é determinante. Não são efetuados envios nem pagamentos.", mismatch: "O IP observado difere da configuração. Verifique o IP de saída deste ambiente e MERCIFACTEUR_AUTHORIZED_IP. Não reutilize automaticamente o IP de outro ambiente.", unknown: "Indisponível", failed: "Não foi possível executar o diagnóstico. Tente novamente.", cost: "Custo indicativo para o operador · carta simples, 1 página", provider: "Resultado do fornecedor", free: "Demonstração ativa: 20 envios gratuitos partilhados por empresa (a cargo do ConstruPilot).", paid: "Fase paga ativa · Stripe · 20 € sem IVA (24 € c/ IVA) / envio ou packs de créditos (5 = 100 €, 10 = 200 €). Alerta admin aos 15/20 envios gratuitos.", quota: "Um envio aceite consome um envio gratuito. Um resultado incerto mantém a vaga; uma recusa confirmada repõe-a.", checked: "Verificado em" },
  pt: { title: "Correio postal", check: "Verificar a ligação postal", pending: "A verificar…", good: "O Merci Facteur respondeu: os preços funcionam neste ambiente.", bad: "A ligação postal necessita de correção.", ips: "IPs autorizados na configuração", observed: "IP de saída observado", note: "A verificação de IP e o Merci Facteur podem usar saídas diferentes. O resultado do fornecedor é determinante. Não são efetuados envios nem pagamentos.", mismatch: "O IP observado difere da configuração. Verifique o IP de saída deste ambiente e MERCIFACTEUR_AUTHORIZED_IP. Não reutilize automaticamente o IP de outro ambiente.", unknown: "Indisponível", failed: "Não foi possível executar o diagnóstico. Tente novamente.", cost: "Custo indicativo para o operador · carta simples, 1 página", provider: "Resultado do fornecedor", free: "Demonstração ativa: 20 envios gratuitos partilhados por empresa (a cargo do ConstruPilot).", paid: "Fase paga ativa · Stripe · 20 € sem IVA (24 € c/ IVA) / envio ou packs de créditos (5 = 100 €, 10 = 200 €). Alerta admin aos 15/20 envios gratuitos.", quota: "Um envio aceite consome um envio gratuito. Um resultado incerto mantém a vaga; uma recusa confirmada repõe-a.", checked: "Verificado em" },
  en: { title: "Postal mail", check: "Check postal connection", pending: "Checking…", good: "Merci Facteur responded: pricing works in this environment.", bad: "The postal connection needs attention.", ips: "Configured authorized IPs", observed: "Observed outbound IP", note: "The IP probe and Merci Facteur may use different outbound paths. The provider result is authoritative. No mail or payment is triggered.", mismatch: "The observed IP differs from configuration. Check this environment's outbound IP and MERCIFACTEUR_AUTHORIZED_IP. Do not automatically reuse another environment's IP.", unknown: "Unavailable", failed: "Unable to run diagnostics. Please retry.", cost: "Indicative operator cost · standard letter, 1 page", provider: "Provider result", free: "Demo active: 20 free letters shared by each company (paid by ConstruPilot).", paid: "Paid phase active · Stripe · €20 excl. VAT (€24 incl.) / letter or credit packs (5 = €100, 10 = €200). Admin alert at 15/20 free letters.", quota: "An accepted letter consumes one free send. Uncertain results keep their slot; confirmed rejection restores it.", checked: "Checked at" },
};

export default function PostalAdminPanel() {
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const { lang } = useI18n();
  const t = LABELS[lang] || LABELS.fr;
  const ui = usePostalCopy();
  const check = async () => {
    setBusy(true); setError(false); setResult(null);
    try { const { data } = await api.get("/admin/postal/diagnostics", { timeout: 65000 }); setResult(data); }
    catch { setError(true); }
    finally { setBusy(false); }
  };
  return <section className="space-y-5 max-w-3xl" data-testid="admin-postal-panel">
    <h2 className="text-lg font-semibold flex items-center gap-2"><Truck size={20} />{t.title}</h2>
    <p className="text-sm border-l-2 border-primary pl-3" data-testid="admin-postal-real-delivery-notice">{ui("liveNotice")}</p>
    <div className="space-y-2 border-y py-4 text-sm">
      <p className="font-medium" data-testid="admin-postal-demo-policy">{ui("trialOffer")}</p>
      <p data-testid="admin-postal-paid-policy">{t.paid}</p>
      <p className="text-muted-foreground" data-testid="admin-postal-demo-quota">{t.quota}</p>
      <p className="text-muted-foreground" data-testid="admin-postal-cost-policy">{ui("costCovered")}</p>
    </div>
    <Button variant="outline" onClick={check} disabled={busy} className="h-auto min-h-11 whitespace-normal text-left" data-testid="admin-postal-diagnose"><RefreshCw size={16} className={busy ? "animate-spin" : ""} />{busy ? t.pending : t.check}</Button>
    {error && <p role="alert" className="text-sm text-red-700" data-testid="admin-postal-error">{t.failed}</p>}
    {result && <div className="space-y-4 text-sm" data-testid="admin-postal-result">
      <p role="status" className="flex items-start gap-2" data-testid="admin-postal-provider-state">{result.provider_ok ? <ShieldCheck size={20} className="shrink-0 text-primary" /> : <AlertTriangle size={20} className="shrink-0 text-amber-600" />}{result.provider_ok ? t.good : t.bad}</p>
      <dl className="grid gap-4 sm:grid-cols-2">
        <div><dt className="text-muted-foreground">{t.ips}</dt><dd className="font-mono break-all" data-testid="admin-postal-configured-ips">{result.configured_ips.join("; ") || t.unknown}</dd></div>
        <div><dt className="text-muted-foreground">{t.observed}</dt><dd className="font-mono break-all" data-testid="admin-postal-observed-ip">{result.observed_ip || t.unknown}</dd></div>
        <div><dt className="text-muted-foreground">{t.provider}</dt><dd data-testid="admin-postal-provider-code">{result.provider_ok ? "OK" : result.provider_error_code || t.unknown}</dd></div>
        <div><dt className="text-muted-foreground">{t.cost}</dt><dd data-testid="admin-postal-provider-price">{result.price_total_ttc != null ? `${result.price_total_ttc.toFixed(2)} € c/ IVA` : t.unknown}</dd></div>
      </dl>
      {result.ip_matches_configuration === false && <p role="alert" className="text-amber-700" data-testid="admin-postal-ip-mismatch">{t.mismatch}</p>}
      <p className="text-xs text-muted-foreground" data-testid="admin-postal-checked-at">{t.checked}: {new Date(result.checked_at).toLocaleString(lang === "pt" ? "pt-PT" : lang)}</p>
    </div>}
    <p className="text-xs text-muted-foreground" data-testid="admin-postal-diagnostic-notice">{t.note}</p>
  </section>;
}