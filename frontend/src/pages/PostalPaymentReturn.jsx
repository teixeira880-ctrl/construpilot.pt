import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2, Loader2, Mail, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { PostalTimeline } from "@/components/radar/PostalTracking";
import { euros } from "@/components/radar/PostalOffer";

const MAX_TRIES = 20;

export default function PostalPaymentReturn() {
  const [params] = useSearchParams();
  const sessionId = params.get("session_id");
  const cancelled = params.get("cancelled") === "1";
  const [view, setView] = useState(null);
  const [state, setState] = useState(cancelled ? "cancelled" : "checking");

  useEffect(() => {
    if (!sessionId || cancelled) { if (!sessionId) setState("error"); return; }
    let stop = false; let tries = 0;
    const poll = async () => {
      try {
        const { data } = await api.get(`/radar/postal/payment/${sessionId}`);
        if (stop) return;
        setView(data);
        const settled = data.payment_status === "paid" && data.fulfillment && !["pending", "processing"].includes(data.fulfillment);
        if (settled) { setState("ok"); return; }
        if (["failed", "expired"].includes(data.payment_status)) { setState("failed"); return; }
        if (tries++ < MAX_TRIES) setTimeout(poll, 2500); else setState("pending");
      } catch { if (!stop) setState("error"); }
    };
    poll();
    return () => { stop = true; };
  }, [sessionId, cancelled]);

  const letter = view?.type === "postal_letter";
  const dispatched = letter && view?.postal?.status === "submitted";
  return (
    <div className="max-w-lg mx-auto surface p-8 mt-12 grid gap-5 text-center" data-testid="postal-payment-return">
      {state === "checking" && <><Loader2 className="h-10 w-10 mx-auto text-primary animate-spin" />
        <p className="font-display text-2xl font-bold">Confirmação do pagamento…</p>
        <p className="text-sm text-muted-foreground">{letter ? "A carta é transmitida à Merci Facteur assim que for confirmada." : "Não feche esta janela."}</p></>}
      {state === "ok" && <>
        {dispatched || !letter ? <CheckCircle2 className="h-14 w-14 mx-auto text-emerald-500" /> : <Mail className="h-14 w-14 mx-auto text-amber-500" />}
        <p className="font-display text-2xl font-bold" data-testid="postal-payment-title">
          {!letter ? `${view.letters}créditos de correio adicionados` : dispatched ? "Carta paga e enviada" : "Pagamento recebido"}
        </p>
        <p className="text-sm text-muted-foreground" data-testid="postal-payment-detail">
          {!letter && `Pagamento de${euros(view.amount_cents)}c/ IVA confirmado · saldo:${view.offer?.credits ?? 0}créditos.`}
          {letter && dispatched && `A Merci Facteur aceitou a carta (n.º${view.postal.envoi_id}) · ${euros(view.amount_cents)} TTC.`}
          {letter && !dispatched && (view.fulfillment === "credited"
            ? `Não foi possível transmitir a carta (${view.fulfillment_error?.message || "preço expirado"}). Foi adicionado um crédito de correio à sua empresa: volte a lançar o envio a partir do radar.`
            : view.postal?.error_message || "Resultado a verificar no acompanhamento das cartas.")}
        </p>
        {view.postal && <div className="text-left surface p-3 rounded-md"><PostalTimeline send={view.postal} /></div>}
      </>}
      {state === "pending" && <><Loader2 className="h-10 w-10 mx-auto text-amber-500" />
        <p className="font-display text-xl font-bold">Pagamento em processamento</p>
        <p className="text-sm text-muted-foreground">A carta partirá automaticamente assim que for confirmada. Consulte o acompanhamento no radar.</p></>}
      {state === "cancelled" && <><XCircle className="h-14 w-14 mx-auto text-muted-foreground" />
        <p className="font-display text-xl font-bold" data-testid="postal-payment-cancelled">Pagamento cancelado</p>
        <p className="text-sm text-muted-foreground">Nenhum montante foi debitado e nenhuma carta foi enviada.</p></>}
      {(state === "failed" || state === "error") && <><XCircle className="h-14 w-14 mx-auto text-red-500" />
        <p className="font-display text-xl font-bold" data-testid="postal-payment-failed">Pagamento não confirmado</p>
        <p className="text-sm text-muted-foreground">Nenhuma carta foi enviada. Verifique o seu histórico de pagamentos antes de tentar novamente.</p></>}
      <div className="flex justify-center gap-3">
        <Link to="/radar"><Button className="rounded-sm" data-testid="postal-payment-back">Voltar ao radar</Button></Link>
      </div>
    </div>
  );
}
