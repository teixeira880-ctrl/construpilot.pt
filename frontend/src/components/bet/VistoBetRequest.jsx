import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ShieldCheck, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const ESTADO = { pendente: "pendente", visado: "visado", recusado: "recusado (reservas)" };

// Pedido de visto do engenheiro sobre o anteprojeto do autopiloto BET (ligação com token, sem conta).
export default function VistoBetRequest({ dossierId }) {
  const [visto, setVisto] = useState(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState({ engineer_name: "", engineer_email: "", engineer_title: "", message: "" });

  useEffect(() => {
    if (!dossierId) return;
    api.get(`/structuro/bet/studies/${dossierId}/visto`).then((r) => setVisto(r.data.visto)).catch(() => {});
  }, [dossierId]);

  const pedir = async () => {
    if (f.engineer_name.trim().length < 2 || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.engineer_email)) return toast.error("Indique o nome e o e-mail do engenheiro.");
    setBusy(true);
    try {
      const { data } = await api.post(`/structuro/bet/studies/${dossierId}/visto`, f);
      setVisto({ status: "pendente", engineer_name: f.engineer_name, share_url: data.share_url, email_sent: data.email_sent });
      setOpen(false);
      toast.success(data.email_sent ? "Pedido de visto enviado ao engenheiro." : "Ligação de visto criada — envie-a ao engenheiro.");
    } catch (e) { toast.error(e?.response?.data?.detail || "Pedido de visto impossível."); }
    finally { setBusy(false); }
  };

  const url = visto?.share_url ? `${window.location.origin}${visto.share_url}` : "";
  return (
    <div className="rounded-md border p-3 grid gap-2 text-xs" data-testid="bet-visto-block">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium flex items-center gap-1"><ShieldCheck className="h-3.5 w-3.5" /> Visto do engenheiro</span>
        {visto && <span className="text-muted-foreground" data-testid="bet-visto-status">Estado: {ESTADO[visto.status] || visto.status}{visto.signatory ? ` · ${visto.signatory}` : ""}</span>}
        {!open && <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => setOpen(true)} data-testid="bet-visto-open">{visto ? "Novo pedido" : "Pedir visto a um engenheiro"}</Button>}
      </div>
      {url && visto?.status === "pendente" && (
        <p className="break-all">Ligação a enviar: <a href={url} target="_blank" rel="noreferrer" className="underline" data-testid="bet-visto-link">{url}</a>
          <button className="underline ml-2" onClick={() => { navigator.clipboard?.writeText(url); toast.success("Ligação copiada"); }}>copiar</button></p>
      )}
      {open && (
        <div className="grid sm:grid-cols-2 gap-2">
          <Input className="h-8" placeholder="Nome do engenheiro" value={f.engineer_name} onChange={(e) => setF({ ...f, engineer_name: e.target.value })} data-testid="bet-visto-name" />
          <Input className="h-8" placeholder="E-mail do engenheiro" value={f.engineer_email} onChange={(e) => setF({ ...f, engineer_email: e.target.value })} data-testid="bet-visto-email" />
          <Input className="h-8" placeholder="Qualidade (facultativo)" value={f.engineer_title} onChange={(e) => setF({ ...f, engineer_title: e.target.value })} />
          <Input className="h-8" placeholder="Mensagem (facultativo)" value={f.message} onChange={(e) => setF({ ...f, message: e.target.value })} />
          <div className="flex gap-2 sm:col-span-2">
            <Button size="sm" onClick={pedir} disabled={busy} data-testid="bet-visto-submit">{busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <ShieldCheck className="h-3 w-3" />} Enviar pedido</Button>
            <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Cancelar</Button>
          </div>
        </div>
      )}
      <p className="text-[11px] text-muted-foreground">O visto regista a revisão do engenheiro na plataforma; não substitui o termo de responsabilidade do autor do projeto de estabilidade.</p>
    </div>
  );
}
