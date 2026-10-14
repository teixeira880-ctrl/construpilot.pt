import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { CheckCircle2, FileSignature, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card } from "@/components/ui/card";
import { SEO } from "@/components/SEO";

const API = process.env.REACT_APP_BACKEND_URL;

export default function SubscrevePublic() {
  const { token } = useParams();
  const [pedido, setPedido] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ nome: "", ordem: "OA", numero: "", especialidade: "arquitetura", observacoes: "" });
  const [sent, setSent] = useState(false);

  useEffect(() => {
    fetch(`${API}/api/publico/autorizacao/subscrever/${token}`)
      .then((r) => r.json())
      .then((d) => {
        if (!d.ok) setErr(d.error || "token_invalido");
        else setPedido(d.pedido);
      })
      .catch(() => setErr("falha_rede"))
      .finally(() => setLoading(false));
  }, [token]);

  const submeter = async () => {
    setErr(null);
    try {
      const r = await fetch(`${API}/api/publico/autorizacao/subscrever/${token}/termo`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form),
      });
      const d = await r.json();
      if (!d.ok) setErr(d.error || "falha");
      else setSent(true);
    } catch (e) { setErr("falha_rede"); }
  };

  if (loading) return <div className="p-8 text-center text-sm text-muted-foreground">A carregar…</div>;

  if (err || !pedido) {
    return (
      <div className="max-w-md mx-auto p-6 py-20 text-center" data-testid="subscrever-erro">
        <ShieldAlert size={48} className="mx-auto mb-4 text-rose-600" />
        <h1 className="text-xl font-semibold mb-2">Link inválido ou já utilizado</h1>
        <p className="text-sm text-muted-foreground">Este pedido de subscrição não foi encontrado ou já foi concluído.</p>
      </div>
    );
  }

  if (sent) {
    return (
      <div className="max-w-md mx-auto p-6 py-20 text-center" data-testid="subscrever-ok">
        <CheckCircle2 size={48} className="mx-auto mb-4 text-emerald-600" />
        <h1 className="text-xl font-semibold mb-2">Termo de responsabilidade registado</h1>
        <p className="text-sm text-muted-foreground">O requerente receberá o processo subscrito. Obrigado.</p>
      </div>
    );
  }

  return (
    <>
      <SEO title="Subscrever processo — ConstruPilot" />
      <div className="max-w-xl mx-auto p-5 py-10" data-testid="subscrever-form">
        <h1 className="text-2xl font-semibold mb-1 flex items-center gap-2"><FileSignature size={22} /> Subscrever processo</h1>
        <p className="text-sm text-muted-foreground mb-5">
          Técnico convidado: <strong>{pedido.tecnico?.nome}</strong> ({pedido.tecnico?.ordem} {pedido.tecnico?.numero})
        </p>

        <Card className="p-4 mb-4 text-sm">
          <div><strong>Procedimento:</strong> {pedido.dossier?.procedimento || "—"}</div>
          {pedido.dossier?.regra_aplicada && <div><strong>Regra:</strong> {pedido.dossier.regra_aplicada}</div>}
        </Card>

        <Card className="p-4 mb-4">
          <h2 className="font-medium mb-3">Termo de responsabilidade (art.º 10.º do RJUE)</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            <div><Label>Nome</Label><Input value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} data-testid="subscrever-nome" /></div>
            <div><Label>Ordem profissional</Label>
              <select className="w-full border rounded h-10 px-3 bg-background" value={form.ordem}
                      onChange={(e) => setForm({ ...form, ordem: e.target.value })} data-testid="subscrever-ordem">
                <option value="OA">OA — Ordem dos Arquitetos</option>
                <option value="OE">OE — Ordem dos Engenheiros</option>
                <option value="OET">OET — Ordem dos Engenheiros Técnicos</option>
              </select>
            </div>
            <div><Label>Número</Label><Input value={form.numero} onChange={(e) => setForm({ ...form, numero: e.target.value })} data-testid="subscrever-numero" /></div>
            <div><Label>Especialidade</Label>
              <select className="w-full border rounded h-10 px-3 bg-background" value={form.especialidade}
                      onChange={(e) => setForm({ ...form, especialidade: e.target.value })} data-testid="subscrever-especialidade">
                <option value="arquitetura">Arquitetura</option>
                <option value="engenheiro_estruturas">Engenharia de estruturas</option>
                <option value="engenheiro_civil">Engenharia civil</option>
                <option value="engenheiro_eletrotecnico">Engenharia eletrotécnica</option>
                <option value="coordenador_projeto">Coordenação de projeto</option>
              </select>
            </div>
            <div className="sm:col-span-2"><Label>Observações (opcional)</Label>
              <Textarea rows={3} value={form.observacoes} onChange={(e) => setForm({ ...form, observacoes: e.target.value })} data-testid="subscrever-obs" />
            </div>
          </div>
          <p className="text-xs text-muted-foreground mt-3">
            Ao submeter, declara sob compromisso de honra que o projeto cumpre as normas legais e regulamentares
            aplicáveis e assume a responsabilidade técnica correspondente nos termos do art.º 10.º do RJUE.
          </p>
        </Card>

        <Button onClick={submeter} disabled={!form.nome || !form.numero} className="w-full" data-testid="subscrever-submeter">
          Subscrever e assumir o termo de responsabilidade
        </Button>
      </div>
    </>
  );
}
