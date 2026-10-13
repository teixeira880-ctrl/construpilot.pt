import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Loader2, MapPin, ShieldCheck, CheckCircle2, Building2, Ruler } from "lucide-react";
import { toast } from "sonner";

const eur = (n) => (Number(n) || 0).toLocaleString("fr-FR") + " €";

export default function ProspectionLanding() {
  const { token } = useParams();
  const [state, setState] = useState("loading"); // loading | ready | notfound | done
  const [d, setD] = useState(null);
  const [form, setForm] = useState({ name: "", email: "", phone: "", message: "", website: "" });
  const [sending, setSending] = useState(false);

  useEffect(() => {
    api.get(`/radar/public/prospection/${token}`)
      .then(({ data }) => { setD(data); setState("ready"); })
      .catch(() => setState("notfound"));
  }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.email) { toast.error("O seu e-mail é obrigatório"); return; }
    setSending(true);
    try {
      await api.post(`/radar/public/prospection/${token}/lead`, form);
      setState("done");
    } catch { toast.error("Impossível enviar, tente novamente"); }
    finally { setSending(false); }
  };

  if (state === "loading")
    return <div className="min-h-screen grid place-items-center bg-stone-50"><Loader2 className="h-6 w-6 animate-spin text-emerald-700" /></div>;

  if (state === "notfound")
    return (
      <div className="min-h-screen grid place-items-center bg-stone-50 px-6 text-center" data-testid="prospection-notfound">
        <div>
          <h1 className="text-2xl font-bold text-stone-800">Lien introuvable</h1>
          <p className="text-stone-500 mt-2">Este link de prospeção já não é válido ou expirou.</p>
        </div>
      </div>
    );

  const c = d.company, o = d.opportunity;

  return (
    <div className="min-h-screen bg-stone-50 text-stone-900" data-testid="prospection-landing">
      <div className="bg-emerald-800 text-white">
        <div className="mx-auto max-w-3xl px-6 py-5 flex items-center gap-3">
          {c.logo_b64 ? (
            <img src={`data:image/png;base64,${c.logo_b64}`} alt={c.name} className="h-10 w-10 rounded-md bg-white object-contain p-1" />
          ) : (
            <span className="h-10 w-10 grid place-items-center rounded-md bg-white/15"><Building2 className="h-5 w-5" /></span>
          )}
          <div>
            <div className="font-extrabold text-lg leading-tight" data-testid="prospection-company">{c.name}</div>
            {c.city && <div className="text-xs text-emerald-100 flex items-center gap-1"><MapPin className="h-3 w-3" /> {c.city}</div>}
          </div>
          {c.verified && (
            <span className="ml-auto inline-flex items-center gap-1 text-xs bg-white/15 rounded-full px-2.5 py-1">
              <ShieldCheck className="h-3.5 w-3.5" /> Pro verificado
            </span>
          )}
        </div>
      </div>

      <div className="mx-auto max-w-3xl px-6 py-10">
        {state === "done" ? (
          <div className="text-center py-16" data-testid="prospection-done">
            <CheckCircle2 className="h-14 w-14 text-emerald-600 mx-auto" />
            <h1 className="text-2xl font-extrabold mt-4">Obrigado, o seu pedido foi recebido!</h1>
            <p className="text-stone-600 mt-2 max-w-md mx-auto">
              {c.name} contactá-lo-á muito em breve para o seu projeto
              {o.commune ? ` à ${o.commune}` : ""}. À très vite.
            </p>
          </div>
        ) : (
          <>
            <p className="text-sm font-semibold text-emerald-700 uppercase tracking-wide">O seu projeto de construção / renovação</p>
            <h1 className="text-3xl sm:text-4xl font-extrabold mt-2 leading-tight" data-testid="prospection-title">
              {o.batiment || "O seu projeto"}{o.commune ? ` — ${o.commune}` : ""}
            </h1>
            <p className="text-stone-600 mt-3 max-w-2xl">
              {c.name} é uma empresa de construção do seu sector. Peça já um
              <b> primeira estimativa gratuita e sem compromisso</b> para o seu projeto.
            </p>

            <div className="grid sm:grid-cols-3 gap-3 mt-6">
              {o.surf_created ? (
                <div className="rounded-xl border border-stone-200 bg-white p-4">
                  <div className="flex items-center gap-1 text-xs text-stone-500"><Ruler className="h-3.5 w-3.5" /> Superfície</div>
                  <div className="text-xl font-extrabold mt-1">{o.surf_created} m²</div>
                </div>
              ) : null}
              {o.my_lot_high ? (
                <div className="rounded-xl border border-stone-200 bg-white p-4 sm:col-span-2">
                  <div className="text-xs text-stone-500">Intervalo indicativo para este tipo de prestação</div>
                  <div className="text-xl font-extrabold mt-1 text-emerald-700">{eur(o.my_lot_low)} – {eur(o.my_lot_high)}</div>
                </div>
              ) : null}
            </div>

            <form onSubmit={submit} className="rounded-2xl border border-stone-200 bg-white p-6 mt-8 grid gap-3 shadow-sm" data-testid="prospection-form">
              <h2 className="text-lg font-bold">Receber a minha estimativa</h2>
              <Input placeholder="O seu nome" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="prospection-name" />
              <Input type="email" required placeholder="O seu e-mail *" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="prospection-email" />
              <Input placeholder="O seu telefone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} data-testid="prospection-phone" />
              <input type="text" name="website" tabIndex={-1} autoComplete="off" value={form.website}
                onChange={(e) => setForm({ ...form, website: e.target.value })}
                style={{ position: "absolute", left: "-9999px", width: 1, height: 1, opacity: 0 }} aria-hidden="true" />
              <Textarea placeholder="Descreva o seu projeto (facultativo)" rows={3} value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })} data-testid="prospection-message" />
              <Button type="submit" disabled={sending} className="rounded-lg bg-emerald-700 hover:bg-emerald-800 h-11 text-base" data-testid="prospection-submit">
                {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Pedir a minha estimativa gratuita"}
              </Button>
              <p className="text-[11px] text-stone-400 text-center">
                As suas coordenadas são transmitidas apenas a {c.name}. Conformément au RGPD, vous pouvez demander leur suppression à tout moment.
              </p>
            </form>
          </>
        )}

        <div className="text-center text-xs text-stone-400 mt-10">
          Desenvolvido por <b>ConstruPilot</b> · Estimez. Comparez. Construisez.
        </div>
      </div>
    </div>
  );
}
