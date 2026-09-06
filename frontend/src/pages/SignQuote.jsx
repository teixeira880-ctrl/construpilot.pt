import { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { CheckCircle2, PenLine, RotateCcw, Download, CreditCard, Loader2 } from "lucide-react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const eur = (n) => (Number(n) || 0).toLocaleString("pt-PT", { style: "currency", currency: "EUR", maximumFractionDigits: 2 });

export default function SignQuote() {
  const { token } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [signing, setSigning] = useState(false);
  const [payBusy, setPayBusy] = useState(false);
  const [signerName, setSignerName] = useState("");
  const canvasRef = useRef(null);
  const [drawing, setDrawing] = useState(false);
  const [hasStroke, setHasStroke] = useState(false);

  const reload = async () => {
    const { data: fresh } = await axios.get(`${API}/quotes/public/sign/${token}`);
    setData(fresh);
    return fresh;
  };

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const { data } = await axios.get(`${API}/quotes/public/sign/${token}`);
        if (alive) setData(data);
      } catch (e) {
        toast.error(e?.response?.data?.detail || "Lien invalide");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [token]);

  // Retour de Stripe : confirme le paiement d'acompte par polling
  useEffect(() => {
    const sid = searchParams.get("session_id");
    if (!sid) return;
    let tries = 0;
    const poll = async () => {
      try {
        const { data: st } = await axios.get(`${API}/quotes/deposit/status/${sid}`);
        if (st.payment_status === "paid") {
          toast.success(`Acompte de ${eur(st.amount)} réglé — merci !`);
          await reload();
          searchParams.delete("session_id"); setSearchParams(searchParams, { replace: true });
          return;
        }
        if (st.payment_status === "expired") {
          toast.error("Session de paiement expirée"); return;
        }
      } catch { /* ignore */ }
      if (++tries < 8) setTimeout(poll, 2000);
    };
    poll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams.get("session_id")]);

  const payDeposit = async () => {
    setPayBusy(true);
    try {
      const { data: r } = await axios.post(`${API}/quotes/public/sign/${token}/deposit/checkout`,
        { origin_url: window.location.origin });
      window.location.href = r.url;
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Paiement indisponible");
      setPayBusy(false);
    }
  };


  const initCanvas = () => {
    const c = canvasRef.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, c.width, c.height);
    ctx.strokeStyle = "#0a0a0a"; ctx.lineWidth = 2.5;
    ctx.lineCap = "round"; ctx.lineJoin = "round";
  };
  useEffect(() => { if (canvasRef.current) initCanvas(); }, [data]);

  const getPos = (e) => {
    const c = canvasRef.current;
    const rect = c.getBoundingClientRect();
    const isTouch = e.touches?.length;
    const x = (isTouch ? e.touches[0].clientX : e.clientX) - rect.left;
    const y = (isTouch ? e.touches[0].clientY : e.clientY) - rect.top;
    return [x * (c.width / rect.width), y * (c.height / rect.height)];
  };
  const start = (e) => { e.preventDefault(); setDrawing(true); const [x, y] = getPos(e);
    const ctx = canvasRef.current.getContext("2d"); ctx.beginPath(); ctx.moveTo(x, y); };
  const move = (e) => { if (!drawing) return; e.preventDefault(); const [x, y] = getPos(e);
    const ctx = canvasRef.current.getContext("2d"); ctx.lineTo(x, y); ctx.stroke(); setHasStroke(true); };
  const end = () => setDrawing(false);
  const clear = () => { initCanvas(); setHasStroke(false); };

  const submit = async () => {
    if (!hasStroke) return toast.error("Signez d'abord dans le cadre");
    if (signerName.trim().length < 2) return toast.error("Indiquez votre nom complet");
    setSigning(true);
    try {
      const b64 = canvasRef.current.toDataURL("image/png").split(",")[1];
      await axios.post(`${API}/quotes/public/sign/${token}`, {
        signature_b64: b64, signer_name: signerName.trim(),
      });
      toast.success("Devis signé avec succès !");
      await reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Signature impossible");
    } finally { setSigning(false); }
  };

  if (loading) return <div className="min-h-screen grid place-items-center bg-background">
    <p className="text-muted-foreground">Chargement du devis…</p></div>;
  if (!data) return <div className="min-h-screen grid place-items-center bg-background">
    <p className="text-destructive">Lien invalide ou expiré.</p></div>;

  return (
    <div className="min-h-screen bg-gradient-to-br from-secondary/30 via-background to-primary/5 p-6">
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="text-center py-8">
          <p className="text-xs uppercase tracking-widest text-primary font-bold">
            {data.company_name || "ConstruPilot"}
          </p>
          <h1 className="font-display text-4xl sm:text-5xl font-extrabold mt-2">
            {data.signed ? "Devis signé" : "Signature de votre devis"}
          </h1>
          {data.contact_line && (
            <p className="text-xs text-muted-foreground mt-2">{data.contact_line}</p>
          )}
        </div>

        <div className="surface p-8 space-y-4" data-testid="sign-summary">
          <div className="flex items-center justify-between">
            <p className="overline">Récapitulatif</p>
            <span className="text-[10px] num text-muted-foreground">Ref · {data.log_id}</span>
          </div>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div><p className="text-muted-foreground text-xs">Client</p>
              <p className="font-bold">{data.client_name || data.client_email}</p></div>
            <div><p className="text-muted-foreground text-xs">Gamme</p>
              <p className="font-bold capitalize">{data.finish || "std"} · {data.floor_material}</p></div>
          </div>
          <div className="bg-primary text-primary-foreground rounded-sm p-6 text-center">
            <p className="text-xs uppercase tracking-widest opacity-90">Total TTC</p>
            <p className="num text-4xl font-extrabold mt-1" data-testid="sign-total">
              {Number(data.total_ttc || 0).toLocaleString("pt-PT", { minimumFractionDigits: 2 })} €
            </p>
          </div>
        </div>

        {data.signed ? (
          <div className="space-y-6">
            <div className="surface p-8 text-center space-y-4" data-testid="sign-done">
              <CheckCircle2 className="h-14 w-14 mx-auto text-primary" />
              <p className="font-display text-xl font-bold">Merci — votre devis est signé.</p>
              <p className="text-xs text-muted-foreground">
                Signé le {new Date(data.signed_at).toLocaleString("pt-PT")}
              </p>
              <a href={`${API}/quotes/public/sign/${token}/pdf`} target="_blank" rel="noopener noreferrer">
                <button className="rounded-sm bg-primary text-primary-foreground px-6 py-3
                                   font-bold hover:bg-orange-600 transition inline-flex items-center gap-2"
                        data-testid="sign-download-pdf">
                  <Download className="h-4 w-4" /> Télécharger le devis signé
                </button>
              </a>
            </div>

            {data.deposit?.paid ? (
              <div className="surface p-6 text-center space-y-2 border-2 border-emerald-500/40 bg-emerald-500/5" data-testid="deposit-paid">
                <CheckCircle2 className="h-10 w-10 mx-auto text-emerald-600" />
                <p className="font-display text-lg font-bold">Acompte réglé — merci !</p>
                <p className="text-sm text-muted-foreground">
                  {eur(data.deposit.paid_amount)} reçu{data.deposit.paid_at ? ` le ${new Date(data.deposit.paid_at).toLocaleDateString("pt-PT")}` : ""}. Votre chantier peut démarrer.
                </p>
              </div>
            ) : data.deposit?.enabled ? (
              <div className="surface p-6 space-y-3 border-2 border-primary/30" data-testid="deposit-block">
                <p className="font-display font-bold inline-flex items-center gap-2">
                  <CreditCard className="h-4 w-4 text-primary" /> Verser l'acompte pour lancer le chantier
                </p>
                <p className="text-sm text-muted-foreground">
                  Acompte de <b>{data.deposit.pct}%</b> soit <b className="text-primary">{eur(data.deposit.amount)}</b> —
                  paiement 100% sécurisé par Stripe.
                </p>
                <button onClick={payDeposit} disabled={payBusy} data-testid="deposit-pay-btn"
                        className="w-full rounded-sm bg-primary text-primary-foreground px-6 py-3 font-bold
                                   hover:bg-orange-600 transition disabled:opacity-50 inline-flex items-center justify-center gap-2">
                  {payBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CreditCard className="h-4 w-4" />}
                  {payBusy ? "Redirection vers le paiement…" : `Payer l'acompte de ${eur(data.deposit.amount)}`}
                </button>
                <p className="text-[10px] text-muted-foreground text-center">Carte de test : 4242 4242 4242 4242 · date future · CVC quelconque</p>
              </div>
            ) : null}
          </div>
        ) : (
          <div className="surface p-8 space-y-4">
            <div className="flex items-center gap-2 mb-2">
              <PenLine className="h-5 w-5 text-primary" />
              <p className="font-display text-lg font-bold">Signez ci-dessous</p>
            </div>
            <label className="block text-xs text-muted-foreground mb-1">Votre nom complet *</label>
            <input value={signerName} onChange={(e) => setSignerName(e.target.value)}
                   placeholder="Prénom Nom"
                   data-testid="sign-name-input"
                   className="w-full rounded-sm border border-border bg-background px-3 py-2 text-sm" />
            <div className="border-2 border-dashed border-border rounded-sm bg-white relative">
              <canvas ref={canvasRef} width={720} height={220}
                      style={{ width: "100%", height: 220, cursor: "crosshair", touchAction: "none" }}
                      data-testid="sign-canvas"
                      onMouseDown={start} onMouseMove={move} onMouseUp={end} onMouseLeave={end}
                      onTouchStart={start} onTouchMove={move} onTouchEnd={end} />
              {!hasStroke && (
                <p className="absolute inset-0 grid place-items-center text-muted-foreground
                              text-xs pointer-events-none">Signez avec la souris ou votre doigt</p>
              )}
            </div>
            <div className="flex gap-2 justify-end">
              <button onClick={clear} data-testid="sign-clear-btn"
                      className="rounded-sm border border-border px-4 py-2 text-sm inline-flex items-center gap-2 hover:bg-secondary">
                <RotateCcw className="h-3 w-3" /> Effacer
              </button>
              <button onClick={submit} disabled={signing || !hasStroke || !signerName.trim()}
                      data-testid="sign-submit-btn"
                      className="rounded-sm bg-primary text-primary-foreground px-6 py-2 text-sm font-bold
                                 hover:bg-orange-600 transition disabled:opacity-40 disabled:cursor-not-allowed
                                 inline-flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4" />
                {signing ? "Envoi…" : "Bon pour accord"}
              </button>
            </div>
            <p className="text-[10px] text-muted-foreground border-t border-border pt-3">
              En signant, vous acceptez le devis estimatif ci-dessus (non contractuel).
              Un contrat détaillé pourra être établi ensuite pour la mise en œuvre.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
