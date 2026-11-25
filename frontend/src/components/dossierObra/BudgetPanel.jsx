import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Plus, FileText, Search, Info } from "lucide-react";
import { api } from "@/lib/api";
import { errMsg } from "./common";

const eur = (v) => (v === null || v === undefined ? "—" : new Intl.NumberFormat("pt-PT", { style: "currency", currency: "EUR" }).format(v));
const num = (v) => (v === null || v === undefined ? "—" : new Intl.NumberFormat("pt-PT", { maximumFractionDigits: 2 }).format(v));
const SRC = { biblioteca: "Biblioteca de preços", manual: "Introduzido", mercado: "Mercado (a confirmar)", "": "Por definir" };

/** Orçamento de UMA especialidade: quantidades a partir das medições, preços da biblioteca ou introduzidos (nunca inventados). */
export function BudgetPanel({ chantierId, specialty, specialtyLabel, measurements, fase, local, onChanged }) {
  const nav = useNavigate();
  const [b, setB] = useState(null);
  const [error, setError] = useState(null);
  const [f, setF] = useState({ title: "", from: "", qty: "", unit: "m²", price: "", source: "manual", reference: "" });
  const [lib, setLib] = useState([]);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => api.get(`/dossier-obra/${chantierId}/orcamento`, { params: { especialidades: specialty } })
    .then(({ data }) => { setB(data.specialties[0] || { lines: [], subtotal_ht: 0, missing_prices: 0 }); setError(null); })
    .catch((e) => setError(e?.response?.status === 403 ? "A sua função não permite ver orçamentos." : errMsg(e))), [chantierId, specialty]);
  useEffect(() => { load(); }, [load]);

  const searchLib = async () => {
    if (!f.title.trim()) return;
    try { const { data } = await api.get("/library", { params: { q: f.title.trim() } }); setLib((data.items || []).slice(0, 6)); if (!(data.items || []).length) toast.info("Sem correspondência na sua biblioteca de preços."); }
    catch { toast.error("Biblioteca indisponível."); }
  };
  const add = async (e) => {
    e.preventDefault();
    const n = (v) => (v === "" ? null : Number(String(v).replace(",", ".")));
    const qty = n(f.qty), price = n(f.price);
    if (!f.title.trim()) { toast.error("Indique a designação."); return; }
    if ((qty !== null && (Number.isNaN(qty) || qty < 0)) || (price !== null && (Number.isNaN(price) || price < 0))) { toast.error("Quantidade ou preço inválido."); return; }
    setBusy(true);
    try {
      await api.post(`/dossier-obra/${chantierId}/itens`, { specialty, kind: "orcamento", title: f.title.trim(), unit: f.unit, phase: fase || null, location_id: local || null,
        from_item_id: f.from || null, quantities: qty !== null ? { orcamentada: qty } : {}, unit_price: price, price_source: price === null ? "" : f.source,
        price_reference: f.reference, status: price === null ? "pendente" : "concluido", validation: price === null ? "por_confirmar" : "confirmado" });
      setF({ ...f, title: "", qty: "", price: "", reference: "" }); setLib([]); load(); onChanged?.();
      toast.success("Linha adicionada");
    } catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };
  const toQuote = async () => {
    setBusy(true);
    try { const { data } = await api.post(`/dossier-obra/${chantierId}/orcamento/rascunho`, { specialties: [specialty] }); toast.success("Orçamento criado em rascunho"); nav(`/devis-editeur/${data.doc_id}`); }
    catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };

  if (error) return <p className="text-sm" role="alert">{error}</p>;
  if (!b) return <p className="text-sm text-muted-foreground" role="status">A carregar o orçamento…</p>;
  return (
    <div className="dob-gap" data-testid="dob-budget">
      <div className="overflow-x-auto dob-boxed">
        <table className="dob-table">
          <thead><tr><th scope="col">Designação</th><th scope="col">Un.</th><th scope="col">Quantidade</th><th scope="col">Preço unit.</th><th scope="col">Total s/ IVA</th><th scope="col">Origem do preço</th></tr></thead>
          <tbody>
            {b.lines.length === 0 && <tr><td colSpan={6} className="text-muted-foreground">Sem linhas. Comece pelas quantidades medidas.</td></tr>}
            {b.lines.map((r) => <tr key={r.item_id}><td>{r.title}{r.from_item_id && <small className="block text-muted-foreground">Quantidade da medição</small>}</td><td>{r.unit}</td><td>{num(r.qty)}</td>
              <td>{eur(r.unit_price)}</td><td><b>{r.total === null ? <span className="dob-pill dob-pill-pendente">A definir</span> : eur(r.total)}</b></td><td>{SRC[r.price_source] || r.price_source}{r.price_reference && <small className="block text-muted-foreground">{r.price_reference}</small>}</td></tr>)}
          </tbody>
          <tfoot><tr><td colSpan={4} className="text-right font-bold">Subtotal {specialtyLabel}</td><td className="font-bold" data-testid="dob-budget-subtotal">{eur(b.subtotal_ht)}</td><td>{b.missing_prices > 0 && <span className="dob-pill dob-pill-pendente">{b.missing_prices} sem preço</span>}</td></tr></tfoot>
        </table>
      </div>
      <form className="dob-boxed dob-card-pad dob-gap" onSubmit={add} data-testid="dob-budget-form">
        <p className="font-semibold">Nova linha de orçamento</p>
        <div className="grid sm:grid-cols-6 gap-2 items-end">
          <label className="dob-field sm:col-span-3"><span>Designação</span><input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="Ex.: Revestimento cerâmico exterior" data-testid="dob-budget-title" /></label>
          <label className="dob-field sm:col-span-3"><span>Quantidade a partir de</span><select value={f.from} onChange={(e) => { const m = measurements.find((x) => x.item_id === e.target.value); setF({ ...f, from: e.target.value, qty: m?.measurement?.quantity ?? f.qty, unit: m?.measurement?.unit || f.unit }); }}>
            <option value="">Introduzir a quantidade</option>{measurements.map((m) => <option key={m.item_id} value={m.item_id}>{m.title} — {num(m.measurement?.quantity)} {m.measurement?.unit}</option>)}</select></label>
          <label className="dob-field"><span>Quantidade</span><input inputMode="decimal" value={f.qty} onChange={(e) => setF({ ...f, qty: e.target.value })} data-testid="dob-budget-qty" /></label>
          <label className="dob-field"><span>Unidade</span><select value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })}>{["m²", "ml", "m", "m³", "un", "kg", "h", "vg"].map((u) => <option key={u}>{u}</option>)}</select></label>
          <label className="dob-field"><span>Preço unit. (€)</span><input inputMode="decimal" value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} placeholder="Vazio = a definir" data-testid="dob-budget-price" /></label>
          <label className="dob-field"><span>Origem</span><select value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })}><option value="manual">Introduzido</option><option value="biblioteca">Biblioteca</option><option value="mercado">Mercado (a confirmar)</option></select></label>
          <button type="button" className="dob-ghost" onClick={searchLib}><Search size={15} /> Biblioteca</button>
          <button type="submit" className="dob-primary" disabled={busy} data-testid="dob-budget-add"><Plus size={16} /> Adicionar</button>
        </div>
        {lib.length > 0 && <div className="flex flex-wrap gap-2">{lib.map((it) => <button key={it.item_id || it.designation} type="button" className="dob-link-chip" onClick={() => { setF({ ...f, title: it.designation, unit: it.unit || f.unit, price: String(it.unit_price_ht ?? ""), source: "biblioteca", reference: `Biblioteca: ${it.designation}` }); setLib([]); }}>{it.designation} · {eur(it.unit_price_ht)}/{it.unit}</button>)}</div>}
        <p className="dob-hint"><Info size={14} /> Primeiro as quantidades, depois os preços. Sem preço, a linha fica «a definir»: nada é inventado.</p>
      </form>
      <div className="flex flex-wrap gap-3 items-center">
        <button type="button" className="dob-primary" onClick={toQuote} disabled={busy || b.lines.length === 0} data-testid="dob-budget-quote"><FileText size={18} /> Orçamentar só esta especialidade</button>
        <p className="dob-hint">Cria um orçamento novo em rascunho no módulo Orçamentos. No fim, «Compilar dossier» junta todas as especialidades no orçamento completo.</p>
      </div>
    </div>
  );
}

/** Orçamento completo: soma dos módulos escolhidos → um único orçamento em rascunho. */
export function CompleteBudget({ chantierId, specialties }) {
  const nav = useNavigate();
  const [b, setB] = useState(null);
  const [busy, setBusy] = useState(false);
  const keys = specialties.join(",");
  useEffect(() => {
    if (!keys) { setB(null); return; }
    api.get(`/dossier-obra/${chantierId}/orcamento`, { params: { especialidades: keys } }).then(({ data }) => setB(data)).catch(() => setB({ forbidden: true }));
  }, [chantierId, keys]);
  if (!b || b.forbidden) return null;
  const withLines = b.specialties.filter((g) => g.lines.length);
  const create = async () => {
    setBusy(true);
    try { const { data } = await api.post(`/dossier-obra/${chantierId}/orcamento/rascunho`, { specialties: withLines.map((g) => g.key) }); toast.success("Orçamento completo criado em rascunho"); nav(`/devis-editeur/${data.doc_id}`); }
    catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <section className="dob-card dob-card-pad dob-gap" data-testid="dob-complete-budget">
      <h2 className="dob-h2">Orçamento completo</h2>
      {withLines.length === 0 ? <p className="text-sm text-muted-foreground">As especialidades escolhidas ainda não têm linhas de orçamento. Abra cada módulo e use o separador «Orçamento».</p> : <>
        <div className="dob-rows dob-boxed">{withLines.map((g) => <div key={g.key} className="dob-row"><div className="dob-row-main"><p>{g.label}</p><p>{g.lines.length} linha(s){g.missing_prices ? ` · ${g.missing_prices} sem preço` : ""}</p></div><b>{eur(g.subtotal_ht)}</b></div>)}
          <div className="dob-row"><div className="dob-row-main"><p className="font-bold">Total s/ IVA</p></div><b data-testid="dob-budget-total">{eur(b.total_ht)}</b></div></div>
        <div className="flex flex-wrap items-center gap-3"><button type="button" className="dob-primary" onClick={create} disabled={busy} data-testid="dob-budget-complete"><FileText size={18} /> Criar orçamento completo</button>
          {b.missing_prices > 0 && <span className="dob-pill dob-pill-pendente">{b.missing_prices} linha(s) sem preço</span>}</div>
      </>}
    </section>
  );
}
