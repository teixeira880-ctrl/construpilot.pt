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
  installation_chantier: ["Instalação de obra (contentor social, vedação, contentor de resíduos)", "forfait"],
  engins_levage: ["Engins & machines (grue, bétonnière)", "forfait"],
  echafaudage: ["Échafaudage (location + montage)", "forfait"],
  protection_securite: ["Protection collective & sécurité (garde-corps, filets, PPSPS)", "forfait"],
  terrassement_complet: ["Terrassement complet (fouilles, remblais)", "forfait"],
  beton_proprete: ["Béton de propreté", "m³"],
  beton_semelle: ["Béton semelles C25/30", "m³"],
  acier_semelle: ["Aços semelles", "kg"],
  fondations_moe: ["Mise en œuvre fondations", "forfait"],
  beton_dalle: ["Béton dallage RDC", "m³"],
  treillis_dalle: ["Treillis ST25C", "kg"],
  coffrage_rive: ["Coffrage de rives", "ml"],
  plancher_etage: ["Plancher d'étage complet", "forfait/niv."],
  mur_isobrique: ["Parede brique isobrique 20", "m²"],
  chainage_beton: ["Béton chaînages", "m³"],
  acier_chainage: ["Aços chaînages", "kg"],
  linteau: ["Linteaux BA", "ml"],
  escalier_beton: ["Béton escalier", "m³"],
  acier_escalier: ["Aços escalier", "kg"],
  charpente_trad: ["Charpente traditionnelle", "forfait"],
  couverture_tuiles: ["Couverture tuiles", "forfait"],
  menuiseries_ext: ["Menuiseries ext. (fenêtres)", "forfait"],
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
      toast.success("Definições enregistrés");
      onSaved?.();
      onClose();
    } catch (e) { toast.error(e?.response?.data?.detail || "Enregistrement impossível"); }
    finally { setBusy(false); }
  };

  const reset = async () => {
    setBusy(true);
    try {
      await api.delete("/pc/settings");
      toast.success("Definições reinicializadas para os valores por omissão");
      onSaved?.();
      onClose();
    } catch { toast.error("Réinitialisation impossível"); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="rounded-sm max-w-2xl max-h-[85vh] overflow-y-auto"
                     data-testid="pc-settings-dialog">
        <DialogHeader>
          <DialogTitle>Definições de l'estudo PC</DialogTitle>
          <DialogDescription>
            Vos prix unitaires (€ HT), la taille d'équipe et le taux horaire sont
            appliqués à toutes vos prochaines études — et recalculés sur l'estudo en cours.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="pc-crew" className="text-xs">Taille d'équipe (compagnons)</Label>
            <Input id="pc-crew" type="number" min="1" max="12" value={crew}
                   onChange={(e) => setCrew(e.target.value)}
                   data-testid="pc-settings-crew-input" className="rounded-sm num" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="pc-rate" className="text-xs">Taux horaire MO (€/h)</Label>
            <Input id="pc-rate" type="number" min="20" max="150" value={rate}
                   onChange={(e) => setRate(e.target.value)}
                   data-testid="pc-settings-rate-input" className="rounded-sm num" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="pc-margin" className="text-xs">Marge bénéficiaire (%) — prix de vente client</Label>
            <Input id="pc-margin" type="number" min="0" max="200" value={margin}
                   onChange={(e) => setMargin(e.target.value)}
                   data-testid="pc-settings-margin-input" className="rounded-sm num" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="pc-deposit" className="text-xs">Sinal en ligne (%) — 0 = désactivé</Label>
            <Input id="pc-deposit" type="number" min="0" max="100" value={depositPct}
                   onChange={(e) => setDepositPct(e.target.value)}
                   data-testid="pc-settings-deposit-input" className="rounded-sm num" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="pc-dep-reminder" className="text-xs">Relance sinal impayé (jours) — 0 = jamais</Label>
            <Input id="pc-dep-reminder" type="number" min="0" max="30" value={depReminderDays}
                   onChange={(e) => setDepReminderDays(e.target.value)}
                   data-testid="pc-settings-deposit-reminder-input" className="rounded-sm num" />
          </div>
          <label className="flex items-center gap-2 text-xs cursor-pointer col-span-2 sm:col-span-1">
            <input type="checkbox" checked={weeklyReport} onChange={(e) => setWeeklyReport(e.target.checked)}
                   data-testid="pc-settings-weekly-checkbox" className="accent-primary" />
            Relatório hebdo par email (chaque lundi)
          </label>
          <label className="flex items-center gap-2 text-xs cursor-pointer col-span-2 sm:col-span-1">
            <input type="checkbox" checked={teamShare} onChange={(e) => setTeamShare(e.target.checked)}
                   data-testid="pc-settings-teamshare-checkbox" className="accent-primary" />
            Partager mes études PC avec mon équipe
          </label>
          <label className="flex items-center gap-2 text-xs cursor-pointer col-span-2 sm:col-span-1">
            <input type="checkbox" checked={teamCanEdit} onChange={(e) => setTeamCanEdit(e.target.checked)}
                   data-testid="pc-settings-teamedit-checkbox" className="accent-primary" />
            Autoriser l'équipe à modifier mes études (sinon lecture seule)
          </label>
          <div className="grid gap-1.5 col-span-2">
            <Label htmlFor="pc-reminder" className="text-xs">
              Relance auto du client si l'estudo n'est pas ouverte après (jours) — 0 = désactivée
            </Label>
            <Input id="pc-reminder" type="number" min="0" max="30" value={reminderDays}
                   onChange={(e) => setReminderDays(e.target.value)}
                   data-testid="pc-settings-reminder-input" className="rounded-sm num w-32" />
          </div>
          <div className="grid gap-1.5">
            <Label className="text-xs">Me prévenir quand le client ouvre l'estudo</Label>
            <select value={notifyMode} onChange={(e) => setNotifyMode(e.target.value)}
                    data-testid="pc-settings-notify-select"
                    className="h-9 rounded-sm border border-input bg-background px-2 text-sm">
              <option value="email">Par email</option>
              <option value="sms">Par SMS</option>
              <option value="both">Email + SMS</option>
              <option value="off">Ne pas me prévenir</option>
            </select>
          </div>
          {(notifyMode === "sms" || notifyMode === "both") && (
            <div className="grid gap-1.5">
              <Label htmlFor="pc-notify-phone" className="text-xs">Número pour les SMS (+33…)</Label>
              <Input id="pc-notify-phone" type="tel" placeholder="+33612345678"
                     value={notifyPhone} onChange={(e) => setNotifyPhone(e.target.value)}
                     data-testid="pc-settings-phone-input" className="rounded-sm num" />
            </div>
          )}
        </div>

        <table className="w-full text-xs border border-border">
          <thead>
            <tr className="bg-muted text-left">
              <th className="p-1.5">Poste</th>
              <th className="p-1.5">Unité</th>
              <th className="p-1.5 text-right">PU matériaux €</th>
              <th className="p-1.5 text-right">PU main d'œuvre €</th>
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
            <RotateCcw className="h-3.5 w-3.5" /> Reinicializar
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
