import { useEffect, useState } from "react";
import { toast } from "sonner";
import { KeyRound, Shield, Eye, EyeOff, Save, RefreshCw, CheckCircle2, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";

/**
 * Página admin protegida para atualização dos secrets do backend (.env)
 * sem passar pelo chat. Nunca guarda valores em state persistente.
 * Rota: /admin/secrets
 */
export default function AdminSecrets() {
  const [status, setStatus] = useState({ configured: [], allowed: [] });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editKey, setEditKey] = useState(null);
  const [editValue, setEditValue] = useState("");
  const [showValue, setShowValue] = useState(false);
  const [restart, setRestart] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/admin/secrets/status");
      setStatus(data || { configured: [], allowed: [] });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Erro a carregar estado das chaves.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const openEdit = (key) => {
    setEditKey(key);
    setEditValue("");
    setShowValue(false);
  };

  const closeEdit = () => {
    setEditKey(null);
    setEditValue("");
    setShowValue(false);
  };

  const save = async () => {
    if (!editValue.trim()) {
      toast.error("Valor vazio.");
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.post("/admin/secrets/update", {
        secrets: [{ key: editKey, value: editValue.trim() }],
        restart_backend: restart,
      });
      setEditValue(""); // apaga imediatamente do state
      if (data?.ok) {
        toast.success(
          `Chave ${editKey} atualizada. ${data.restart_scheduled ? "Backend a reiniciar…" : ""}`.trim()
        );
        closeEdit();
        if (data.restart_scheduled) {
          // Aguarda 4s pelo restart e recarrega o status
          setTimeout(load, 4000);
        } else {
          load();
        }
      } else {
        toast.error(data?.detail || "Falha inesperada.");
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Erro ao guardar.");
    } finally {
      setSaving(false);
    }
  };

  const configuredMap = Object.fromEntries((status.configured || []).map((s) => [s.key, s]));

  return (
    <div data-testid="admin-secrets-page" className="mx-auto max-w-4xl px-6 py-10 space-y-8">
      <header className="space-y-2">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-emerald-500/10 p-3">
            <Shield className="h-6 w-6 text-emerald-500" />
          </div>
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Chaves API · Zona protegida</h1>
            <p className="text-sm text-muted-foreground">
              Introduza as chaves de integração diretamente aqui. Os valores nunca
              passam pelo chat, nunca são registados em logs, e são gravados no
              <code className="mx-1 rounded bg-muted px-1 py-0.5 text-xs">.env</code>
              do backend.
            </p>
          </div>
        </div>
      </header>

      <div className="rounded-lg border bg-amber-500/5 p-4 text-sm">
        <div className="flex items-start gap-2">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
          <div>
            <strong>Regras de segurança</strong>: apenas as chaves na lista abaixo
            podem ser atualizadas. As chaves críticas do sistema (base de dados,
            JWT, VAPID) estão bloqueadas e não aparecem aqui. Após guardar, o
            backend reinicia automaticamente (aguarde ~4 s).
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Chaves permitidas ({status.allowed?.length || 0})</h2>
        <Button
          data-testid="admin-secrets-refresh"
          variant="outline" size="sm" onClick={load} disabled={loading}
        >
          <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Atualizar
        </Button>
      </div>

      <ul className="space-y-2">
        {(status.allowed || []).map((key) => {
          const cfg = configuredMap[key];
          return (
            <li
              key={key}
              data-testid={`secret-row-${key}`}
              className="flex items-center justify-between rounded-lg border bg-card px-4 py-3"
            >
              <div className="flex items-center gap-3">
                <KeyRound className="h-4 w-4 text-muted-foreground" />
                <div>
                  <div className="font-mono text-sm">{key}</div>
                  <div className="text-xs text-muted-foreground">
                    {cfg ? (
                      <span className="inline-flex items-center gap-1">
                        <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                        Configurado · <code>{cfg.hint}</code> ({cfg.length} chars)
                      </span>
                    ) : (
                      <span className="text-muted-foreground">Não configurado</span>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {cfg && <Badge variant="outline" className="border-emerald-500/40 text-emerald-500">Ativo</Badge>}
                <Button
                  data-testid={`secret-edit-${key}`}
                  size="sm"
                  variant={cfg ? "outline" : "default"}
                  onClick={() => openEdit(key)}
                >
                  {cfg ? "Substituir" : "Definir"}
                </Button>
              </div>
            </li>
          );
        })}
      </ul>

      <Dialog open={!!editKey} onOpenChange={(o) => (!o ? closeEdit() : null)}>
        <DialogContent data-testid="secret-edit-dialog">
          <DialogHeader>
            <DialogTitle>Atualizar {editKey}</DialogTitle>
            <DialogDescription>
              Cole aqui o valor. Nunca será mostrado depois de guardado. O valor
              não é registado em logs.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="secret-value">Valor</Label>
              <div className="flex gap-2">
                <Input
                  id="secret-value"
                  data-testid="secret-value-input"
                  type={showValue ? "text" : "password"}
                  autoComplete="off"
                  spellCheck={false}
                  placeholder={`Ex.: sk_live_…`}
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                />
                <Button
                  data-testid="secret-value-toggle"
                  type="button" size="icon" variant="outline"
                  onClick={() => setShowValue((v) => !v)}
                  aria-label={showValue ? "Ocultar" : "Mostrar"}
                >
                  {showValue ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                data-testid="secret-restart-toggle"
                checked={restart}
                onChange={(e) => setRestart(e.target.checked)}
              />
              Reiniciar backend automaticamente após guardar
            </label>
          </div>
          <DialogFooter>
            <Button
              data-testid="secret-cancel-btn"
              variant="outline" onClick={closeEdit} disabled={saving}
            >
              Cancelar
            </Button>
            <Button
              data-testid="secret-save-btn"
              onClick={save} disabled={saving || !editValue.trim()}
            >
              <Save className="mr-2 h-4 w-4" />
              {saving ? "A guardar…" : "Guardar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
