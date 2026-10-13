import { useState } from "react";
import axios from "axios";
import { Send, CheckCircle2 } from "lucide-react";

const BASE = process.env.REACT_APP_BACKEND_URL;
const EMPTY = { name: "", email: "", phone: "", postal_code: "", city: "", address: "", description: "", website: "" };

export function QuoteRequestForm({ slug, companyName, accent }) {
  const [form, setForm] = useState(EMPTY);
  const [state, setState] = useState("idle");
  const [error, setError] = useState("");
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const field = "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2";

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (form.description.trim().length < 10) return setError("Descreva as suas obras em poucas palavras (mínimo 10 caracteres).");
    setState("sending");
    try {
      await axios.post(`${BASE}/api/public/company/${slug}/quote-request`, form);
      setState("done");
    } catch (err) {
      setState("idle");
      const d = err?.response?.data?.detail;
      setError(err?.response?.status === 429 ? "Demasiados pedidos enviados a partir deste dispositivo. Tente novamente mais tarde." : (typeof d === "string" ? d : "Envio impossível de momento. Verifique o seu e-mail e tente novamente."));
    }
  };

  if (state === "done") return (
    <div className="rounded-2xl border p-8 text-center" style={{ borderColor: accent }} data-testid="quote-request-success">
      <CheckCircle2 className="h-10 w-10 mx-auto" style={{ color: accent }} />
      <h3 className="text-xl font-semibold mt-3">Pedido enviado</h3>
      <p className="text-slate-600 mt-2">{companyName} recebeu o seu pedido de orçamento e voltará a contactá-lo através do endereço <strong>{form.email}</strong>.</p>
    </div>
  );

  return (
    <form onSubmit={submit} className="rounded-2xl border p-6 md:p-8 grid gap-4" style={{ borderColor: accent }} data-testid="quote-request-form">
      <div><h3 className="text-xl font-semibold">Pedir um orçamento gratuito</h3><p className="text-sm text-slate-600 mt-1">Descreva as suas obras: {companyName} responde-lhe diretamente.</p></div>
      <div className="grid sm:grid-cols-2 gap-3">
        <label className="text-sm grid gap-1">Nome e apelido *<input className={field} value={form.name} onChange={set("name")} required minLength={2} maxLength={120} data-testid="quote-request-name" /></label>
        <label className="text-sm grid gap-1">E-mail *<input type="email" className={field} value={form.email} onChange={set("email")} required data-testid="quote-request-email" /></label>
        <label className="text-sm grid gap-1">Telefone<input type="tel" className={field} value={form.phone} onChange={set("phone")} maxLength={40} data-testid="quote-request-phone" /></label>
        <label className="text-sm grid gap-1">Código postal<input className={field} value={form.postal_code} onChange={set("postal_code")} maxLength={12} data-testid="quote-request-postal" /></label>
        <label className="text-sm grid gap-1 sm:col-span-2">Morada da obra<input className={field} value={form.address} onChange={set("address")} maxLength={200} data-testid="quote-request-address" /></label>
      </div>
      <label className="text-sm grid gap-1">As suas obras *<textarea className={field} rows={4} value={form.description} onChange={set("description")} required minLength={10} maxLength={3000} placeholder="Ex.: Remodelação completa de uma casa de banho de 6 m², substituição da banheira por um duche…" data-testid="quote-request-description" /></label>
      <input type="text" name="website" value={form.website} onChange={set("website")} tabIndex={-1} autoComplete="off" aria-hidden="true" className="hidden" />
      {error && <p className="text-sm text-red-600" role="alert" data-testid="quote-request-error">{error}</p>}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-slate-500">As suas coordenadas são transmitidas apenas a {companyName}.</p>
        <button type="submit" disabled={state === "sending"} className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg text-white font-medium disabled:opacity-60" style={{ background: accent }} data-testid="quote-request-submit">
          <Send className="h-4 w-4" /> {state === "sending" ? "A enviar…" : "Enviar o meu pedido"}
        </button>
      </div>
    </form>
  );
}
