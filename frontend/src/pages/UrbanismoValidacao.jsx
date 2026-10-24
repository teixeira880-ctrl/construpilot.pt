import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ShieldCheck, FileDown, Loader2, CheckCircle2, XCircle } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const RES = { conforme: "Conforme", nao_conforme: "Não conforme", sem_dados: "Sem dados", atencao: "Atenção", informativo: "Informativo" };
const pt = (v, nd = 2) => (v === null || v === undefined ? "—" : typeof v === "number" ? v.toLocaleString("pt-PT", { maximumFractionDigits: nd }) : String(v));

// Página pública (sem conta): o técnico revê o processo de urbanismo e valida ou emite reservas.
export default function UrbanismoValidacao() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ signatario: "", ordem: "", numero_inscricao: "", decisao: "validar", comentario: "" });

  const load = () => api.get(`/publico/urbanismo-validacao/${token}`).then((r) => setData(r.data)).catch(() => setErr("Ligação de validação inválida ou expirada."));
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [token]);

  const zip = async () => {
    setBusy(true);
    try {
      const { data: blob } = await api.get(`/publico/urbanismo-validacao/${token}/export.zip`, { responseType: "blob", timeout: 120000 });
      const u = URL.createObjectURL(blob); const a = document.createElement("a");
      a.href = u; a.download = "processo-urbanismo.zip"; a.click(); setTimeout(() => URL.revokeObjectURL(u), 1000);
    } catch { toast.error("Transferência indisponível."); }
    finally { setBusy(false); }
  };

  const submit = async () => {
    if (form.signatario.trim().length < 2) return toast.error("Indique o seu nome.");
    if (form.decisao === "reservas" && !form.comentario.trim()) return toast.error("Indique as reservas.");
    setBusy(true);
    try { const { data: r } = await api.post(`/publico/urbanismo-validacao/${token}/assinar`, form); toast.success(r.status === "validado" ? "Validação registada. Obrigado." : "Reservas enviadas."); await load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Envio impossível."); }
    finally { setBusy(false); }
  };

  const q = data?.quadro;
  const done = data && data.status !== "pendente";
  return (
    <div className="min-h-screen bg-background" data-testid="urb-validacao-page">
      <header className="border-b bg-card"><div className="max-w-3xl mx-auto px-4 py-4 flex items-center gap-3">
        <Link to="/" className="font-bold text-lg">ConstruPilot</Link>
        <span className="text-xs text-muted-foreground flex items-center gap-1"><ShieldCheck size={14} /> Revisão de processo de urbanismo</span>
      </div></header>
      <main className="max-w-3xl mx-auto px-4 py-8 grid gap-6">
        {err && <p className="text-sm text-red-600" data-testid="urb-validacao-erro">{err}</p>}
        {!data && !err && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> A carregar…</div>}
        {data && (<>
          <div className="grid gap-1">
            <div className="text-xs uppercase tracking-widest text-primary font-semibold">Pedido de revisão</div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight" data-testid="urb-validacao-titulo">{data.processo}</h1>
            <p className="text-sm text-muted-foreground">{data.tipo_obra_label}{data.concelho ? ` · ${data.concelho}` : ""} · procedimento indicativo: {data.procedimento_label}</p>
            {data.mensagem && <p className="text-sm italic">«{data.mensagem}»</p>}
          </div>
          {q && <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
            {[["Área do terreno", `${pt(q.area_terreno_m2)} m²`], ["Implantação", `${pt(q.area_implantacao_m2)} m²`], ["Construção", `${pt(q.area_construcao_m2)} m²`], ["Pisos", q.n_pisos],
              ["Io", `${pt(q.indice_ocupacao_pct, 1)} %`], ["Iu", pt(q.indice_utilizacao, 3)], ["Altura da fachada", `${pt(q.altura_fachada_m)} m`], ["Altura total", `${pt(q.altura_total_m)} m`]].map(([k, v]) => (
              <div key={k} className="border rounded-md p-2"><span className="text-muted-foreground">{k}</span><p className="text-base font-semibold">{v}</p></div>))}
          </div>}
          <div className="border rounded-lg p-3 text-sm grid gap-1">
            <p className="font-semibold">Verificações</p>
            {(data.verificacoes || []).map((it) => <p key={it.codigo} className="text-xs"><b>{RES[it.resultado] || it.resultado}</b> — {it.titulo}: {pt(it.valor)} / limite {pt(it.limite)} {it.unidade}</p>)}
            {data.parametros_em_falta?.length > 0 && <p className="text-xs text-muted-foreground">Parâmetros municipais não indicados: {data.parametros_em_falta.join("; ")}.</p>}
          </div>
          <Button variant="outline" onClick={zip} disabled={busy} className="w-fit gap-2" data-testid="urb-validacao-zip"><FileDown className="h-4 w-4" /> Descarregar o processo (ZIP)</Button>
          <p className="text-xs italic text-muted-foreground border-l-2 border-amber-400 pl-3">{data.aviso}</p>
          {done ? (
            <div className={`rounded-md border p-4 ${data.status === "validado" ? "border-emerald-400 bg-emerald-50 dark:bg-emerald-950/20" : "border-red-400 bg-red-50 dark:bg-red-950/20"}`} data-testid="urb-validacao-decisao">
              <p className="font-semibold flex items-center gap-2">{data.status === "validado" ? <><CheckCircle2 className="h-4 w-4 text-emerald-600" /> Processo validado</> : <><XCircle className="h-4 w-4 text-red-600" /> Reservas emitidas</>}</p>
              <p className="text-sm mt-1">Por {data.signatario}{data.numero_inscricao ? ` · ${data.ordem || "Ordem"} n.º ${data.numero_inscricao}` : ""} em {data.decided_at ? new Date(data.decided_at).toLocaleDateString("pt-PT") : ""}</p>
              {data.comentario && <p className="text-sm mt-2 italic">«{data.comentario}»</p>}
            </div>
          ) : (
            <div className="rounded-md border p-4 grid gap-3" data-testid="urb-validacao-form">
              <p className="text-sm font-medium">Validar ou emitir reservas</p>
              <div className="grid sm:grid-cols-3 gap-3">
                <label className="grid gap-1 text-xs sm:col-span-3">Nome completo<Input value={form.signatario} onChange={(e) => setForm({ ...form, signatario: e.target.value })} data-testid="urb-validacao-nome" /></label>
                <label className="grid gap-1 text-xs">Ordem
                  <select className="h-9 rounded-md border bg-background px-2 text-sm" value={form.ordem} onChange={(e) => setForm({ ...form, ordem: e.target.value })}>
                    <option value="">—</option><option value="OA">Ordem dos Arquitectos</option><option value="OE">Ordem dos Engenheiros</option><option value="OET">Ordem dos Engenheiros Técnicos</option>
                  </select>
                </label>
                <label className="grid gap-1 text-xs">N.º de inscrição<Input value={form.numero_inscricao} onChange={(e) => setForm({ ...form, numero_inscricao: e.target.value })} /></label>
                <label className="grid gap-1 text-xs">Decisão
                  <select className="h-9 rounded-md border bg-background px-2 text-sm" value={form.decisao} onChange={(e) => setForm({ ...form, decisao: e.target.value })} data-testid="urb-validacao-decisao-select">
                    <option value="validar">Valido o processo</option><option value="reservas">Emito reservas</option>
                  </select>
                </label>
              </div>
              <label className="grid gap-1 text-xs">Comentário / reservas {form.decisao === "reservas" && <span className="text-red-600">(obrigatório)</span>}
                <textarea rows={3} className="rounded-md border bg-background p-2 text-sm" value={form.comentario} onChange={(e) => setForm({ ...form, comentario: e.target.value })} data-testid="urb-validacao-comentario" />
              </label>
              <p className="text-[11px] text-muted-foreground">Esta revisão fica registada na plataforma e não substitui o termo de responsabilidade do autor do projeto (art.º 10.º do RJUE).</p>
              <Button onClick={submit} disabled={busy} className="w-full sm:w-auto" data-testid="urb-validacao-submit">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />} {form.decisao === "validar" ? "Validar" : "Enviar reservas"}</Button>
            </div>
          )}
        </>)}
      </main>
    </div>
  );
}
