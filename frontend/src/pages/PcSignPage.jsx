import { useCallback, useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { CheckCircle2, Circle, Clock, CreditCard, FileDown, HardHat, Hammer, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SignatureCanvas } from "@/components/pc/SignatureCanvas";
import { api, eur, num } from "@/lib/api";

export default function PcSignPage() {
  const { token } = useParams();
  const [searchParams] = useSearchParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [signature, setSignature] = useState(null);
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);
  const [payBusy, setPayBusy] = useState("");

  const load = useCallback(() => {
    api.get(`/pc/sign/${token}`)
      .then(({ data: d }) => setData(d))
      .catch((e) => setError(e?.response?.data?.detail || "Ligação inválida ou expirada"));
  }, [token]);
  useEffect(load, [load]);

  // Retour de Stripe : confirme le paiement (acompte ou situation) par polling
  useEffect(() => {
    const sid = searchParams.get("session_id");
    if (!sid) return;
    let tries = 0;
    const timer = setInterval(async () => {
      tries += 1;
      try {
        const { data: st } = await api.get(`/pc/deposit/status/${sid}`);
        if (st.payment_status === "paid") {
          clearInterval(timer);
          toast.success(`Pagamento de ${eur(st.amount)} recebido — obrigado!`);
          load();
        } else if (["expired", "failed"].includes(st.payment_status) || tries > 12) {
          clearInterval(timer);
          if (["expired", "failed"].includes(st.payment_status)) {
            toast.error("O pagamento não foi concluído — pode tentar novamente");
          }
        }
      } catch {
        if (tries > 12) clearInterval(timer);
      }
    }, 2500);
    return () => clearInterval(timer);
  }, [searchParams, load]);

  const accept = async () => {
    if (name.trim().length < 2) return toast.error("Indique o seu nome completo");
    if (!agree) return toast.error("Assinale a caixa de aceitação");
    setBusy(true);
    try {
      const { data: r } = await api.post(`/pc/sign/${token}/accept`,
        { name: name.trim(), signature_data: signature });
      setData((p) => ({
        ...p, accepted: true, accepted_at: r.accepted_at,
        accepted_by: name.trim(), accepted_signature: signature,
      }));
      toast.success("Estudo aceite — obrigado!");
    } catch (e) { toast.error(e?.response?.data?.detail || "Aceitação impossível"); }
    finally { setBusy(false); }
  };

  const payDeposit = async () => {
    setPayBusy("deposit");
    try {
      const { data: r } = await api.post(`/pc/sign/${token}/deposit/checkout`,
        { origin_url: window.location.origin });
      window.location.href = r.url;
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Pagamento indisponível — tente novamente mais tarde");
      setPayBusy("");
    }
  };

  const paySituation = async (sitId) => {
    setPayBusy(sitId);
    try {
      const { data: r } = await api.post(`/pc/sign/${token}/situation/${sitId}/checkout`,
        { origin_url: window.location.origin });
      window.location.href = r.url;
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Pagamento indisponível — tente novamente mais tarde");
      setPayBusy("");
    }
  };

  if (error) {
    return (
      <div className="min-h-screen grid place-items-center bg-background p-6">
        <p className="text-muted-foreground" data-testid="pc-sign-error">{error}</p>
      </div>
    );
  }
  if (!data) {
    return <div className="min-h-screen grid place-items-center bg-background">
      <p className="text-muted-foreground animate-pulse">Carregamento do estudo…</p>
    </div>;
  }

  const t = data.totals || {};
  const dep = data.deposit || {};
  const prog = data.progress || {};
  const sits = data.situations || [];
  const bill = data.billing || {};
  const paidPct = bill.total_ttc > 0 ? Math.min(100, Math.round((100 * bill.paid) / bill.total_ttc)) : 0;

  return (
    <div className="min-h-screen bg-background py-10 px-4" data-testid="pc-sign-page">
      <div className="max-w-2xl mx-auto space-y-6">
        <header className="space-y-1">
          <p className="overline flex items-center gap-2 text-primary">
            <HardHat className="h-4 w-4" /> {data.company || "ConstruPilot"}
          </p>
          <h1 className="font-display text-2xl sm:text-3xl font-extrabold">
            Estudo de estrutura — {data.filename || "o seu projeto"}
          </h1>
          <p className="text-sm text-muted-foreground">
            Elaborado a {String(data.generated_at || "").slice(0, 10)}
            {data.planning?.total_days ? ` · obra estimada ${data.planning.total_days} jours (${data.planning.total_weeks} semanas)` : ""}
          </p>
        </header>

        {data.pro && (data.pro.name || data.pro.photo) && (
          <div className="surface p-4 flex items-center gap-4" data-testid="pc-sign-pro-card">
            {data.pro.photo ? (
              <img src={data.pro.photo} alt={data.pro.name || "O seu interlocutor"}
                   className="h-14 w-14 rounded-full object-cover border border-border shrink-0"
                   data-testid="pc-sign-pro-photo" />
            ) : (
              <div className="h-14 w-14 rounded-full bg-muted flex items-center justify-center font-bold text-muted-foreground shrink-0">
                {(data.pro.name || "?").charAt(0).toUpperCase()}
              </div>
            )}
            <div className="min-w-0">
              <p className="text-[10px] uppercase tracking-wide text-muted-foreground">O seu interlocutor</p>
              <p className="font-semibold truncate" data-testid="pc-sign-pro-name">{data.pro.name}</p>
              <p className="text-xs text-muted-foreground truncate">
                {[data.pro.phone, data.pro.email].filter(Boolean).join(" · ")}
              </p>
              {data.pro.contact_line && (
                <p className="text-xs text-muted-foreground truncate">{data.pro.contact_line}</p>
              )}
            </div>
          </div>
        )}

        {data.demandes?.length > 0 && (
          <ul className="text-sm text-muted-foreground space-y-0.5">
            {data.demandes.slice(0, 4).map((d, i) => <li key={i}>• {d}</li>)}
          </ul>
        )}

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[["Betão", `${num(t.beton_m3, 1)} m³`], ["Aços", `${num(t.acier_kg)} kg`],
            ["Tijolos térmicos", `${num(t.briques_u)} u`], ["Total c/ IVA", eur(t.ttc)]].map(([k, v]) => (
            <div key={k} className="surface p-3">
              <p className="text-[10px] text-muted-foreground">{k}</p>
              <p className="font-display font-bold num">{v}</p>
            </div>
          ))}
        </div>

        <table className="w-full text-sm border border-border">
          <tbody>
            {(data.lots || []).map((l) => (
              <tr key={l.lot} className="border-t border-border first:border-t-0">
                <td className="p-2">{l.lot}</td>
                <td className="p-2 text-right num font-semibold">{eur(l.total)}</td>
              </tr>
            ))}
            <tr className="border-t-2 border-primary/40 bg-muted/40">
              <td className="p-2 font-bold">Total s/ IVA / IVA 20 % / c/ IVA</td>
              <td className="p-2 text-right num font-bold text-primary">
                {eur(t.ht)} / {eur(t.tva)} / {eur(t.ttc)}
              </td>
            </tr>
          </tbody>
        </table>

        {data.accepted ? (
          <div className="rounded-sm border-2 border-emerald-500/50 bg-emerald-500/10 p-5 text-center space-y-2"
               data-testid="pc-sign-accepted">
            <CheckCircle2 className="h-8 w-8 text-emerald-500 mx-auto" />
            <p className="font-display font-bold text-emerald-600">Estudo aceite</p>
            <p className="text-sm text-muted-foreground">
              le {String(data.accepted_at || "").slice(0, 10)} par <b>{data.accepted_by}</b>
            </p>
            {data.accepted_signature && (
              <img src={data.accepted_signature} alt="Assinatura do cliente"
                   className="mx-auto h-16 bg-white rounded-sm border border-border px-3"
                   data-testid="pc-sign-signature-img" />
            )}
          </div>
        ) : (
          <div className="surface p-5 space-y-3" data-testid="pc-sign-form">
            <p className="font-semibold flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-primary" /> Aceitar esta proposta online
            </p>
            <Input placeholder="O seu nome completo" value={name}
                   onChange={(e) => setName(e.target.value)}
                   data-testid="pc-sign-name-input" className="rounded-sm" />
            <SignatureCanvas onChange={setSignature} />
            <label className="flex items-start gap-2 text-xs text-muted-foreground cursor-pointer">
              <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)}
                     data-testid="pc-sign-agree-checkbox" className="mt-0.5 accent-primary" />
              Tomei conhecimento do estudo de estrutura acima (quantidades e montantes indicativos) e aceito-o como base de trabalho.
            </label>
            <Button onClick={accept} disabled={busy} className="rounded-sm w-full gap-2"
                    data-testid="pc-sign-accept-btn">
              <CheckCircle2 className="h-4 w-4" /> {busy ? "…" : "Aceito este estudo"}
            </Button>
          </div>
        )}

        {data.accepted && dep.pct > 0 && (dep.paid ? (
          <div className="rounded-sm border-2 border-emerald-500/50 bg-emerald-500/10 p-4 text-center space-y-1"
               data-testid="pc-deposit-paid">
            <CreditCard className="h-6 w-6 text-emerald-500 mx-auto" />
            <p className="font-display font-bold text-emerald-600">
              Sinal de {eur(dep.paid_amount || dep.amount)} pago
            </p>
            {dep.paid_at && (
              <p className="text-xs text-muted-foreground">le {String(dep.paid_at).slice(0, 10)}</p>
            )}
            <a href={`${api.defaults.baseURL}/pc/sign/${token}/deposit/invoice`}
               target="_blank" rel="noreferrer"
               className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary underline underline-offset-2"
               data-testid="pc-deposit-invoice-link">
              <FileDown className="h-3.5 w-3.5" /> Descarregar a fatura de adiantamento
            </a>
          </div>
        ) : (
          <div className="surface p-5 space-y-3" data-testid="pc-deposit-block">
            <p className="font-semibold flex items-center gap-2">
              <CreditCard className="h-4 w-4 text-primary" /> Pagar o sinal para iniciar a obra
            </p>
            <p className="text-sm text-muted-foreground">
              Sinal de <b>{num(dep.pct)} %</b> — ou seja <b>{eur(dep.amount)}</b> num total de {eur(t.ttc)} c/ IVA. Pagamento seguro por cartão bancário (Stripe).
            </p>
            <Button onClick={payDeposit} disabled={payBusy === "deposit"}
                    className="rounded-sm w-full gap-2" data-testid="pc-deposit-pay-btn">
              <CreditCard className="h-4 w-4" />
              {payBusy === "deposit" ? "A redirecionar para o pagamento…" : `Pagar o sinal de ${eur(dep.amount)}`}
            </Button>
          </div>
        ))}

        {data.accepted && prog.total > 0 && (
          <div className="surface p-5 space-y-3" data-testid="pc-progress-client">
            <p className="font-semibold flex items-center gap-2">
              <Hammer className="h-4 w-4 text-primary" /> Progresso da sua obra — {prog.pct} %
            </p>
            <div className="h-2 bg-muted rounded-full overflow-hidden">
              <div className="h-full bg-primary transition-all" style={{ width: `${prog.pct}%` }} />
            </div>
            <ul className="space-y-1.5">
              {(prog.phases || []).map((ph, i) => (
                <li key={i} className="flex items-center gap-2 text-sm"
                    data-testid={`pc-progress-client-phase-${i}`}>
                  {ph.done ? (
                    <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                  ) : (
                    <Circle className="h-4 w-4 text-muted-foreground/40 shrink-0" />
                  )}
                  <span className={ph.done ? "text-muted-foreground line-through" : ""}>
                    {ph.name}
                  </span>
                </li>
              ))}
            </ul>
            {prog.updated_at && (
              <p className="text-[10px] text-muted-foreground">
                Última atualização em {String(prog.updated_at).slice(0, 10)}
              </p>
            )}
          </div>
        )}

        {data.accepted && (sits.length > 0 || bill.paid > 0) && (
          <div className="surface p-5 space-y-3" data-testid="pc-billing-client">
            <p className="font-semibold flex items-center gap-2">
              <CreditCard className="h-4 w-4 text-primary" /> Faturação da obra
            </p>
            <p className="text-sm text-muted-foreground">
              Pago: <b className="text-emerald-600">{eur(bill.paid)}</b> sur {eur(bill.total_ttc)} c/ IVA
              {bill.remaining_to_pay > 0 ? <> — restante <b>{eur(bill.remaining_to_pay)}</b></> : " — obra liquidada, obrigado!"}
            </p>
            <div className="h-2 bg-muted rounded-full overflow-hidden">
              <div className="h-full bg-emerald-500 transition-all" style={{ width: `${paidPct}%` }} />
            </div>
            <div className="space-y-2">
              {sits.map((s) => (
                <div key={s.sit_id} className="border border-border rounded-sm px-3 py-2 space-y-1.5"
                     data-testid={`pc-client-situation-${s.sit_no}`}>
                  <div className="flex items-center justify-between gap-2 text-sm">
                    <span>
                      <b>{s.is_final ? "Fatura de saldo" : `Auto de medição n.º ${s.sit_no}`}</b>
                      <span className="text-muted-foreground text-xs"> · {s.invoice_no}</span>
                    </span>
                    <span className="num font-semibold shrink-0">{eur(s.amount)}</span>
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <a href={`${api.defaults.baseURL}/pc/sign/${token}/situation/${s.sit_id}/invoice`}
                       target="_blank" rel="noreferrer"
                       className="inline-flex items-center gap-1 text-xs text-primary underline underline-offset-2"
                       data-testid={`pc-client-situation-${s.sit_no}-invoice`}>
                      <FileDown className="h-3 w-3" /> Fatura PDF
                    </a>
                    {s.paid ? (
                      <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-600"
                            data-testid={`pc-client-situation-${s.sit_no}-paid`}>
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        Paga a {new Date(s.paid_at).toLocaleDateString("pt-PT")}
                      </span>
                    ) : (
                      <Button size="sm" onClick={() => paySituation(s.sit_id)}
                              disabled={payBusy === s.sit_id}
                              className="h-7 rounded-sm text-xs gap-1.5"
                              data-testid={`pc-client-situation-${s.sit_no}-pay-btn`}>
                        <CreditCard className="h-3 w-3" />
                        {payBusy === s.sit_id ? "A redirecionar…" : `Pagar ${eur(s.amount)} par carte`}
                      </Button>
                    )}
                  </div>
                </div>
              ))}
              {sits.length === 0 && (
                <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                  <Clock className="h-3.5 w-3.5" /> Os próximos autos de medição aparecerão aqui.
                </p>
              )}
            </div>
          </div>
        )}

        <p className="text-[10px] text-muted-foreground text-center">
          Documento indicativo gerado por ConstruPilot — não constitui um orçamento contratual.
        </p>
      </div>
    </div>
  );
}
