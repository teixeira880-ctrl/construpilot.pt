import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";

const API = process.env.REACT_APP_BACKEND_URL;

export default function AutorizacaoObrasPanel() {
  const [cfg, setCfg] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    try {
      const r = await fetch(`${API}/api/admin/autorizacao-obras/settings`, { credentials: "include" });
      const d = await r.json();
      if (d.ok) setCfg(d.settings);
    } catch { /* ignore */ }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/admin/autorizacao-obras/settings`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, credentials: "include",
        body: JSON.stringify(cfg),
      });
      const d = await r.json();
      if (d.ok) { setCfg(d.settings); toast.success("Preferências guardadas."); }
      else toast.error("Falha ao guardar.");
    } finally { setLoading(false); }
  };

  if (!cfg) return <Card className="p-4">A carregar…</Card>;

  const set = (k, v) => setCfg({ ...cfg, [k]: v });

  return (
    <Card className="p-5" data-testid="admin-autorizacao-panel">
      <h3 className="text-lg font-semibold mb-1">Autorização de obras — venda</h3>
      <p className="text-sm text-muted-foreground mb-4">
        O diagnóstico guiado é sempre gratuito. Esta secção controla a venda do processo completo
        (requerimento + memória + ficha + estimativa). A venda está desativada por defeito.
      </p>

      <div className="space-y-4">
        <label className="flex items-center justify-between gap-4 p-3 rounded border">
          <span><strong>Venda ativa</strong><br /><span className="text-xs text-muted-foreground">Quando desativada, o botão de pagamento devolve 403.</span></span>
          <Switch checked={!!cfg.sale_enabled} onCheckedChange={(v) => set("sale_enabled", v)} data-testid="admin-autorizacao-sale-enabled" />
        </label>

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <Label htmlFor="pr">Preço (€)</Label>
            <Input id="pr" type="number" min="0" step="1" value={cfg.price_eur || 0}
                   onChange={(e) => set("price_eur", parseFloat(e.target.value) || 0)}
                   data-testid="admin-autorizacao-price" />
          </div>
          <div>
            <Label htmlFor="cur">Moeda</Label>
            <Input id="cur" value={cfg.currency || "eur"} onChange={(e) => set("currency", e.target.value)}
                   data-testid="admin-autorizacao-currency" />
          </div>
        </div>

        <label className="flex items-center justify-between gap-4 p-3 rounded border">
          <span>Incluído no plano Pro</span>
          <Switch checked={!!cfg.included_in_pro} onCheckedChange={(v) => set("included_in_pro", v)} data-testid="admin-autorizacao-pro" />
        </label>
        <label className="flex items-center justify-between gap-4 p-3 rounded border">
          <span>Incluído no plano Business</span>
          <Switch checked={!!cfg.included_in_business} onCheckedChange={(v) => set("included_in_business", v)} data-testid="admin-autorizacao-business" />
        </label>

        <div>
          <Label htmlFor="pname">Nome do produto no Stripe</Label>
          <Input id="pname" value={cfg.stripe_product_name || ""}
                 onChange={(e) => set("stripe_product_name", e.target.value)}
                 data-testid="admin-autorizacao-pname" />
        </div>

        <Button onClick={save} disabled={loading} data-testid="admin-autorizacao-save">
          {loading ? "A guardar…" : "Guardar"}
        </Button>
      </div>

      <TecnicosParceirosEditor />
    </Card>
  );
}


function TecnicosParceirosEditor() {
  const [lista, setLista] = useState([]);
  const [novo, setNovo] = useState({ nome: "", email: "", especialidade: "arquitetura", regiao: "", preco_indicativo_eur: 0, prazo_dias: 7, numero: "" });
  const [loading, setLoading] = useState(false);

  const load = async () => {
    const r = await fetch(`${API}/api/admin/autorizacao-obras/tecnicos`, { credentials: "include" });
    const d = await r.json();
    if (d.ok) setLista(d.tecnicos || []);
  };
  useEffect(() => { load(); }, []);

  const criar = async () => {
    if (!novo.nome || !novo.email.includes("@")) return;
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/admin/autorizacao-obras/tecnicos`, {
        method: "POST", headers: { "Content-Type": "application/json" }, credentials: "include",
        body: JSON.stringify(novo),
      });
      const d = await r.json();
      if (d.ok) {
        setLista([...lista, d.tecnico]);
        setNovo({ nome: "", email: "", especialidade: "arquitetura", regiao: "", preco_indicativo_eur: 0, prazo_dias: 7, numero: "" });
        toast.success("Técnico adicionado.");
      }
    } finally { setLoading(false); }
  };

  const toggleAtivo = async (t) => {
    await fetch(`${API}/api/admin/autorizacao-obras/tecnicos/${t.id}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, credentials: "include",
      body: JSON.stringify({ ativo: !t.ativo }),
    });
    load();
  };

  const eliminar = async (id) => {
    await fetch(`${API}/api/admin/autorizacao-obras/tecnicos/${id}`, {
      method: "DELETE", credentials: "include",
    });
    load();
  };

  return (
    <div className="mt-8 pt-6 border-t" data-testid="admin-tecnicos-editor">
      <h4 className="font-semibold mb-3">Catálogo de técnicos parceiros</h4>
      <p className="text-xs text-muted-foreground mb-4">
        Em produção, o JSON em disco está vazio. Os técnicos reais são geridos aqui e guardados em MongoDB.
        Nunca mostrar perfis ao público sem acordo escrito prévio.
      </p>

      <div className="space-y-2 mb-4">
        {lista.length === 0 && <p className="text-sm text-muted-foreground">Sem técnicos no catálogo.</p>}
        {lista.map((t) => (
          <div key={t.id} className="flex items-center justify-between p-3 rounded border text-sm" data-testid={`admin-tecnico-${t.id}`}>
            <div>
              <div className="font-medium">{t.nome} <span className={`ml-2 text-xs ${t.ativo ? "text-emerald-700" : "text-muted-foreground"}`}>{t.ativo ? "ativo" : "inativo"}</span></div>
              <div className="text-xs text-muted-foreground">{t.email} · {t.especialidade} · {t.regiao || "—"} · {t.preco_indicativo_eur || 0} €</div>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => toggleAtivo(t)} data-testid={`admin-tecnico-toggle-${t.id}`}>{t.ativo ? "Desativar" : "Ativar"}</Button>
              <Button variant="outline" size="sm" onClick={() => eliminar(t.id)} data-testid={`admin-tecnico-del-${t.id}`}>Eliminar</Button>
            </div>
          </div>
        ))}
      </div>

      <div className="p-3 rounded border bg-muted/30">
        <h5 className="font-medium mb-3 text-sm">Adicionar técnico</h5>
        <div className="grid gap-2 sm:grid-cols-2">
          <div><Label className="text-xs">Nome*</Label><Input value={novo.nome} onChange={(e) => setNovo({ ...novo, nome: e.target.value })} data-testid="admin-tecnico-novo-nome" /></div>
          <div><Label className="text-xs">E-mail*</Label><Input value={novo.email} onChange={(e) => setNovo({ ...novo, email: e.target.value })} data-testid="admin-tecnico-novo-email" /></div>
          <div><Label className="text-xs">Especialidade</Label>
            <select value={novo.especialidade} onChange={(e) => setNovo({ ...novo, especialidade: e.target.value })}
                    className="w-full border rounded h-10 px-2 bg-background" data-testid="admin-tecnico-novo-esp">
              <option value="arquitetura">Arquiteto</option>
              <option value="engenheiro_estruturas">Engenheiro de estruturas</option>
              <option value="engenheiro_civil">Engenheiro civil</option>
              <option value="engenheiro_eletrotecnico">Engenheiro eletrotécnico</option>
              <option value="engenheiro_mecanico">Engenheiro mecânico</option>
              <option value="coordenador_projeto">Coordenador de projeto</option>
            </select>
          </div>
          <div><Label className="text-xs">Nº da ordem</Label><Input value={novo.numero} onChange={(e) => setNovo({ ...novo, numero: e.target.value })} data-testid="admin-tecnico-novo-numero" /></div>
          <div><Label className="text-xs">Região</Label><Input value={novo.regiao} onChange={(e) => setNovo({ ...novo, regiao: e.target.value })} data-testid="admin-tecnico-novo-regiao" /></div>
          <div><Label className="text-xs">Preço indicativo (€)</Label><Input type="number" value={novo.preco_indicativo_eur} onChange={(e) => setNovo({ ...novo, preco_indicativo_eur: parseFloat(e.target.value) || 0 })} data-testid="admin-tecnico-novo-preco" /></div>
        </div>
        <Button size="sm" className="mt-3" onClick={criar} disabled={loading} data-testid="admin-tecnico-novo-criar">Adicionar</Button>
      </div>
    </div>
  );
}
