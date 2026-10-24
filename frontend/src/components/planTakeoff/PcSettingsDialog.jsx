import { useEffect, useState } from "react";
import { toast } from "sonner";
import { RotateCcw, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";

const PRICE_LABELS = {
  installation_chantier: ["Instalação de estaleiro (base de vida, vedação, contentor)", "forfait"],
  engins_levage: ["Máquinas & equipamentos (grua, betoneira)", "forfait"],
  echafaudage: ["Andaime (aluguer + montagem)", "forfait"],
  protection_securite: ["Proteção coletiva & segurança (guarda-corpos, redes, PPSPS)", "forfait"],
  terrassement_complet: ["Terraplanagem completa (escavações, aterros)", "forfait"],
  beton_proprete: ["Betão de limpeza", "m³"],
  beton_semelle: ["Betão sapatas C25/30", "m³"],
  acier_semelle: ["Aços sapatas", "kg"],
  fondations_moe: ["Execução de fundações", "forfait"],
  beton_dalle: ["Betão laje RDC", "m³"],
  treillis_dalle: ["Malha ST25C", "kg"],
  coffrage_rive: ["Cofragem de bordas", "ml"],
  plancher_etage: ["Pavimento de piso completo", "forfait/niv."],
  mur_isobrique: ["Parede tijolo isotérmico 20", "m²"],
  chainage_beton: ["Betão cintas", "m³"],
  acier_chainage: ["Aços cintas", "kg"],
  linteau: ["Padieiras BA", "ml"],
  escalier_beton: ["Betão escada", "m³"],
  acier_escalier: ["Aços escada", "kg"],
  charpente_trad: ["Carpintaria tradicional", "forfait"],
  couverture_tuiles: ["Cobertura de telhas", "forfait"],
  menuiseries_ext: ["Caixilharias ext. (janelas)", "forfait"],
};

export default function PcSettingsDialog({ open, onClose, onSaved }) {
  const [prices, setPrices] = useState({});
  const [crew, setCrew] = useState(3);
  const [rate, setRate] = useState(35);
  const [margin, setMargin] = useState(30);
  const [depositPct, setDepositPct] = useState(30);
  const [depReminderDays, setDepReminderDays] = useState(3);
  const [weeklyReport, setWeeklyReport] = useState(true);
  const [teamShare, setTeamShare] = useState(true);
  const [teamCanEdit, setTeamCanEdit] = useState(false);
  const [reminderDays, setReminderDays] = useState(3);
  const [notifyMode, setNotifyMode] = useState("email");
  const [notifyPhone, setNotifyPhone] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    api.get("/pc/settings").then(({ data }) => {
      const d = data.defaults || {};
      const s = data.settings || {};
      const merged = {};
      Object.entries(d.unit_prices || {}).forEach(([k, v]) => {
        const c = (s.unit_prices || {})[k] || {};
        merged[k] = { mat: c.mat ?? v.mat, mo: c.mo ?? v.mo };
      });
      setPrices(merged);
      setCrew(s.crew_size ?? d.crew_size ?? 3);
      setRate(s.hourly_rate_eur ?? d.hourly_rate_eur ?? 35);
      setMargin(s.margin_pct ?? d.margin_pct ?? 30);
      setDepositPct(s.deposit_pct ?? d.deposit_pct ?? 30);
      setDepReminderDays(s.deposit_reminder_days ?? d.deposit_reminder_days ?? 3);
      setWeeklyReport(s.weekly_report ?? d.weekly_report ?? true);
      setTeamShare(s.team_share ?? d.team_share ?? true);
      setTeamCanEdit(s.team_can_edit ?? d.team_can_edit ?? false);
      setReminderDays(s.reminder_days ?? d.reminder_days ?? 3);
      setNotifyMode(s.notify_on_open ?? d.notify_on_open ?? "email");
      setNotifyPhone(s.notify_phone ?? "");
    }).catch(() => toast.error("Carregamento das definições impossível"));
  }, [open]);

  const setP = (key, field, val) =>
    setPrices((prev) => ({ ...prev, [key]: { ...prev[key], [field]: val } }));

  const save = async () => {
    setBusy(true);
    try {
      const unit_prices = {};
      Object.entries(prices).forEach(([k, v]) => {
        unit_prices[k] = { mat: parseFloat(v.mat) || 0, mo: parseFloat(v.mo) || 0 };
      });
      await api.put("/pc/settings", {
        unit_prices, crew_size: parseInt(crew, 10) || 3,
        hourly_rate_eur: parseFloat(rate) || 35,
        margin_pct: Math.max(0, parseFloat(margin) || 0),
        deposit_pct: Math.max(0, parseFloat(depositPct) || 0),
        deposit_reminder_days: Math.max(0, parseInt(depReminderDays, 10) || 0),
        weekly_report: !!weeklyReport,
        team_share: !!teamShare,
        team_can_edit: !!teamCanEdit,
        reminder_days: Math.max(0, parseInt(reminderDays, 10) || 0),
        notify_on_open: notifyMode,
        notify_phone: notifyPhone.trim() || null,
      });
      toast.success("Definições guardadas");
      onSaved?.();
      onClose();
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível guardar"); }
    finally { setBusy(false); }
  };

  const reset = async () => {
    setBusy(true);
    try {
      await api.delete("/pc/settings");
      toast.success("Definições reiniciadas para os valores predefinidos");
      onSaved?.();
      onClose();
    } catch { toast.error("Reinício impossível"); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="rounded-sm max-w-2xl max-h-[85vh] overflow-y-auto"
                     data-testid="pc-settings-dialog">
        <DialogHeader>
          <DialogTitle>Definições do estudo de licença</DialogTitle>
          <DialogDescription>
            Os seus preços unitários (€ s/ IVA), o tamanho da equipa e a taxa horária são aplicados a todos os seus próximos estudos — e recalculados no estudo em curso.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="pc-crew" className="text-xs">Dimensão da equipa (operários)</Label>
            <Input id="pc-crew" type="number" min="1" max="12" value={crew}
                   onChange={(e) => setCrew(e.target.value)}
                   data-testid="pc-settings-crew-input" className="rounded-sm num" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="pc-rate" className="text-xs">Taxa horária MO (€/h)</Label>
            <Input id="pc-rate" type="number" min="20" max="150" value={rate}
                   onChange={(e) => setRate(e.target.value)}
                   data-testid="pc-settings-rate-input" className="rounded-sm num" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="pc-margin" className="text-xs">Margem de lucro (%) — preço de venda ao cliente</Label>
            <Input id="pc-margin" type="number" min="0" max="200" value={margin}
                   onChange={(e) => setMargin(e.target.value)}
                   data-testid="pc-settings-margin-input" className="rounded-sm num" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="pc-deposit" className="text-xs">Sinal online (%) — 0 = desativado</Label>
            <Input id="pc-deposit" type="number" min="0" max="100" value={depositPct}
                   onChange={(e) => setDepositPct(e.target.value)}
                   data-testid="pc-settings-deposit-input" className="rounded-sm num" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="pc-dep-reminder" className="text-xs">Lembrete de sinal por pagar (dias) — 0 = nunca</Label>
            <Input id="pc-dep-reminder" type="number" min="0" max="30" value={depReminderDays}
                   onChange={(e) => setDepReminderDays(e.target.value)}
                   data-testid="pc-settings-deposit-reminder-input" className="rounded-sm num" />
          </div>
          <label className="flex items-center gap-2 text-xs cursor-pointer col-span-2 sm:col-span-1">
            <input type="checkbox" checked={weeklyReport} onChange={(e) => setWeeklyReport(e.target.checked)}
                   data-testid="pc-settings-weekly-checkbox" className="accent-primary" />
            Relatório semanal por e-mail (todas as segundas)
          </label>
          <label className="flex items-center gap-2 text-xs cursor-pointer col-span-2 sm:col-span-1">
            <input type="checkbox" checked={teamShare} onChange={(e) => setTeamShare(e.target.checked)}
                   data-testid="pc-settings-teamshare-checkbox" className="accent-primary" />
            Partilhar os meus estudos de licenciamento com a minha equipa
          </label>
          <label className="flex items-center gap-2 text-xs cursor-pointer col-span-2 sm:col-span-1">
            <input type="checkbox" checked={teamCanEdit} onChange={(e) => setTeamCanEdit(e.target.checked)}
                   data-testid="pc-settings-teamedit-checkbox" className="accent-primary" />
            Autorizar a equipa a modificar os meus estudos (senão apenas leitura)
          </label>
          <div className="grid gap-1.5 col-span-2">
            <Label htmlFor="pc-reminder" className="text-xs">
              Lembrete automático ao cliente se o estudo não for aberto após (dias) — 0 = desativado
            </Label>
            <Input id="pc-reminder" type="number" min="0" max="30" value={reminderDays}
                   onChange={(e) => setReminderDays(e.target.value)}
                   data-testid="pc-settings-reminder-input" className="rounded-sm num w-32" />
          </div>
          <div className="grid gap-1.5">
            <Label className="text-xs">Avisar-me quando o cliente abrir o estudo</Label>
            <select value={notifyMode} onChange={(e) => setNotifyMode(e.target.value)}
                    data-testid="pc-settings-notify-select"
                    className="h-9 rounded-sm border border-input bg-background px-2 text-sm">
              <option value="email">Por email</option>
              <option value="sms">Por SMS</option>
              <option value="both">Email + SMS</option>
              <option value="off">Não me avisar</option>
            </select>
          </div>
          {(notifyMode === "sms" || notifyMode === "both") && (
            <div className="grid gap-1.5">
              <Label htmlFor="pc-notify-phone" className="text-xs">Número para SMS (+33…)</Label>
              <Input id="pc-notify-phone" type="tel" placeholder="+33612345678"
                     value={notifyPhone} onChange={(e) => setNotifyPhone(e.target.value)}
                     data-testid="pc-settings-phone-input" className="rounded-sm num" />
            </div>
          )}
        </div>

        <table className="w-full text-xs border border-border">
          <thead>
            <tr className="bg-muted text-left">
              <th className="p-1.5">Artigo</th>
              <th className="p-1.5">Un.</th>
              <th className="p-1.5 text-right">PU materiais €</th>
              <th className="p-1.5 text-right">PU mão de obra €</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(PRICE_LABELS).map(([key, [label, unit]]) => (
              <tr key={key} className="border-t border-border">
                <td className="p-1.5 font-medium">{label}</td>
                <td className="p-1.5 text-muted-foreground">{unit}</td>
                <td className="p-1.5">
                  <Input type="number" min="0" step="0.05" value={prices[key]?.mat ?? ""}
                         onChange={(e) => setP(key, "mat", e.target.value)}
                         data-testid={`pc-price-${key}-mat`}
                         className="rounded-sm h-7 text-right num text-xs" />
                </td>
                <td className="p-1.5">
                  <Input type="number" min="0" step="0.05" value={prices[key]?.mo ?? ""}
                         onChange={(e) => setP(key, "mo", e.target.value)}
                         data-testid={`pc-price-${key}-mo`}
                         className="rounded-sm h-7 text-right num text-xs" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={reset} disabled={busy}
                  className="rounded-sm gap-2 mr-auto" data-testid="pc-settings-reset-btn">
            <RotateCcw className="h-3.5 w-3.5" /> Reiniciar
          </Button>
          <Button variant="outline" onClick={onClose} className="rounded-sm"
                  data-testid="pc-settings-cancel">Cancelar</Button>
          <Button onClick={save} disabled={busy} className="rounded-sm gap-2"
                  data-testid="pc-settings-save-btn">
            <Save className="h-3.5 w-3.5" /> {busy ? "…" : "Guardar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
