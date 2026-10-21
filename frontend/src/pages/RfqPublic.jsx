import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { Loader2, Send, CheckCircle2, HardHat } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const eur = (n) => (Number(n) || 0).toLocaleString("pt-PT", { style: "currency", currency: "EUR" });

export default function RfqPublic() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [prices, setPrices] = useState({});
  const [note, setNote] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    axios.get(`${API}/public/rfq/${token}`)
      .then(({ data: d }) => {
        setData(d);
        setPrices(d.prices || {});
        setName(d.recipient?.name || "");
        if (d.responded_at) setDone(true);
      })
      .catch((e) => setError(e?.response?.data?.detail || "Ligação inválida ou expirada"));
  }, [token]);

  const total = (data?.lines || []).reduce(
    (s, l) => s + (Number(prices[l.line_id]) || 0) * (l.qty || 0), 0);

  const submit = async () => {
    const clean = Object.fromEntries(Object.entries(prices)
      .filter(([, v]) => Number(v) > 0).map(([k, v]) => [k, Number(v)]));
    if (!Object.keys(clean).length) { toast.error("Introduza pelo menos um preço unitário"); return; }
    setBusy(true);
    try {
      await axios.post(`${API}/public/rfq/${token}`, { prices: clean, note, contact_name: name });
      setDone(true);
      toast.success("Proposta transmitida");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Envio impossível");
    } finally { setBusy(false); }
  };

  if (error) return <Centered testid="rfq-error">{error}</Centered>;
  if (!data) return <Centered testid="rfq-loading"><Loader2 className="h-5 w-5 animate-spin" /></Centered>;

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-3xl mx-auto px-5 py-10" data-testid="rfq-public-page">
        <div className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-primary">
          <HardHat className="h-3.5 w-3.5" /> Pedido de preço
        </div>
        <h1 className="font-display text-3xl sm:text-4xl font-bold mt-2">{data.lot}</h1>
        <p className="text-sm text-muted-foreground mt-2">
          {data.company} consulta-o · resposta pretendida até <b>{data.due_date}</b>
        </p>
        {data.message && (
          <p className="mt-3 rounded-sm border border-border bg-muted/40 p-3 text-sm" data-testid="rfq-message">{data.message}</p>
        )}

        {done ? (
          <div className="mt-6 rounded-lg border border-primary/30 bg-primary/5 p-5 flex gap-3" data-testid="rfq-done">
            <CheckCircle2 className="h-5 w-5 text-primary shrink-0" />
            <div className="text-sm">
              <p className="font-semibold">Proposta transmitida — {eur(total)} HT</p>
              <p className="text-muted-foreground mt-1">{data.company} recebeu os seus preços. Obrigado.</p>
            </div>
          </div>
        ) : (
          <>
            <div className="mt-6 rounded-sm border border-border overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-secondary/40">
                  <tr><th className="text-left p-2">Prestação</th><th className="p-2">Qtd.</th>
                    <th className="p-2">U.</th><th className="p-2 text-right">O seu PU s/ IVA</th>
                    <th className="p-2 text-right">Total s/ IVA</th></tr>
                </thead>
                <tbody>
                  {data.lines.map((l) => (
                    <tr key={l.line_id} className="border-t border-border/60" data-testid={`rfq-line-${l.line_id}`}>
                      <td className="p-2">{l.designation}</td>
                      <td className="p-2 text-center num">{l.qty ?? "—"}</td>
                      <td className="p-2 text-center">{l.unit}</td>
                      <td className="p-2 text-right">
                        <Input type="number" min={0} step="0.01" value={prices[l.line_id] ?? ""}
                          onChange={(e) => setPrices({ ...prices, [l.line_id]: e.target.value })}
                          className="rounded-sm h-8 w-24 num text-right ml-auto"
                          data-testid={`rfq-pu-${l.line_id}`} />
                      </td>
                      <td className="p-2 text-right num">
                        {eur((Number(prices[l.line_id]) || 0) * (l.qty || 0))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1.5 text-xs text-muted-foreground">O seu nome / empresa
                <Input value={name} onChange={(e) => setName(e.target.value)} className="rounded-sm h-10"
                  data-testid="rfq-name" />
              </label>
              <div className="text-right self-end">
                <p className="text-xs text-muted-foreground">Total da sua proposta</p>
                <p className="num text-2xl font-extrabold text-primary" data-testid="rfq-total">{eur(total)}</p>
              </div>
            </div>
            <label className="grid gap-1.5 text-xs text-muted-foreground mt-3">Observações (prazos, variantes, exclusões)
              <Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} className="rounded-sm"
                data-testid="rfq-note" />
            </label>
            <Button onClick={submit} disabled={busy} className="rounded-sm gap-2 mt-4" data-testid="rfq-submit">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />} Enviar a minha proposta
            </Button>
            <p className="text-[11px] text-muted-foreground mt-2">
              Nenhuma conta necessária. Os seus preços só são visíveis por {data.company}.
            </p>
          </>
        )}
      </div>
    </div>
  );
}

const Centered = ({ children, testid }) => (
  <div className="min-h-screen grid place-items-center px-6 text-sm text-muted-foreground" data-testid={testid}>
    {children}
  </div>
);
