import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { KeyRound, CheckCircle2, AlertTriangle, Eye, EyeOff } from "lucide-react";

export default function BabyLoveGrowthSettingsPanel() {
  const [status, setStatus] = useState(null);
  const [apiKey, setApiKey] = useState("");
  const [secret, setSecret] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [showSecret, setShowSecret] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get("/admin/babylovegrowth/status");
      setStatus(data);
    } catch {
      /* silêncio: a UI mostra o estado em falta */
    }
  };

  useEffect(() => {
    load();
  }, []);

  const save = async () => {
    if (!apiKey.trim() && !secret.trim()) {
      toast.error("Preencha pelo menos um dos campos");
      return;
    }
    setBusy(true);
    try {
      const payload = {};
      if (apiKey.trim()) payload.api_key = apiKey.trim();
      if (secret.trim()) payload.webhook_secret = secret.trim();
      await api.put("/admin/babylovegrowth/credentials", payload);
      toast.success("Credenciais guardadas");
      setApiKey("");
      setSecret("");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Impossível guardar");
    } finally {
      setBusy(false);
    }
  };

  const configured = status?.configured;
  const secretSet = status?.webhook_secret_set;

  return (
    <div className="rounded-xl border border-border bg-card p-5" data-testid="blg-settings">
      <h3 className="font-semibold flex items-center gap-2">
        <KeyRound className="h-4 w-4 text-primary" /> BabyLoveGrowth — credenciais
      </h3>
      <p className="text-xs text-muted-foreground mt-1">
        Cole aqui a chave da API e o segredo do webhook (48 caracteres). Os valores são guardados de forma segura e nunca aparecem em registos nem na interface após gravação.
      </p>

      <div className="mt-3 space-y-1.5 text-sm">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-2">
            {configured ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
            ) : (
              <AlertTriangle className="h-4 w-4 text-amber-500" />
            )}
            Chave da API
          </span>
          <span className="text-[11px] text-muted-foreground" data-testid="blg-apikey-state">
            {configured ? "definida" : "em falta"}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-2">
            {secretSet ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
            ) : (
              <AlertTriangle className="h-4 w-4 text-amber-500" />
            )}
            Segredo do webhook
          </span>
          <span className="text-[11px] text-muted-foreground" data-testid="blg-secret-state">
            {secretSet ? "definido" : "em falta"}
          </span>
        </div>
      </div>

      <div className="grid gap-3 mt-4">
        <div>
          <label className="text-xs font-medium block mb-1">Nova chave da API</label>
          <div className="flex gap-2">
            <Input
              type={showKey ? "text" : "password"}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="Cole a chave da BabyLoveGrowth"
              autoComplete="off"
              data-testid="blg-api-key"
            />
            <Button
              size="sm"
              variant="outline"
              onClick={() => setShowKey((v) => !v)}
              type="button"
              data-testid="blg-toggle-key"
            >
              {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </Button>
          </div>
        </div>
        <div>
          <label className="text-xs font-medium block mb-1">Novo segredo do webhook (48 caracteres)</label>
          <div className="flex gap-2">
            <Input
              type={showSecret ? "text" : "password"}
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              placeholder="Cole o segredo do webhook"
              autoComplete="off"
              data-testid="blg-webhook-secret"
            />
            <Button
              size="sm"
              variant="outline"
              onClick={() => setShowSecret((v) => !v)}
              type="button"
              data-testid="blg-toggle-secret"
            >
              {showSecret ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </div>

      <div className="flex gap-2 mt-4">
        <Button
          onClick={save}
          disabled={busy || (!apiKey.trim() && !secret.trim())}
          data-testid="blg-save"
        >
          Guardar
        </Button>
      </div>
      <p className="text-[11px] text-muted-foreground mt-2">
        Dica: pode guardar só um dos campos de cada vez. O outro mantém o valor anterior.
      </p>
    </div>
  );
}
