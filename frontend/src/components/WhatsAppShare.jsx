import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  MessageCircle, Copy, ExternalLink, Link as LinkIcon,
  Send, Eye, Clock, Smartphone,
} from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogDescription,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { api, eur } from "@/lib/api";

const cleanPhone = (raw) => (raw || "").replace(/[^\d+]/g, "").replace(/^00/, "+");

const buildMessage = ({ project, estimation, link }) => {
  const total = estimation?.total_avg;
  const min = estimation?.total_min;
  const max = estimation?.total_max;
  const surface = project?.surface || estimation?.surface;
  const parts = [
    `📐 *Estimation ConstruPilot — ${project?.name || "Projet"}*`,
    surface ? `Área:${surface} m²` : null,
    total ? `Orçamento estimado: *${eur(total)}*${min && max ? ` (${eur(min)} – ${eur(max)})` : ""}` : null,
    estimation?.finish_level_name ? `Finition : ${estimation.finish_level_name}` : null,
    "",
    link ? `Ver o detalhe 👉${link}` : null,
    "",
    "— ConstruPilot",
  ].filter(Boolean);
  return parts.join("\n");
};

const EXPIRY_OPTIONS = [
  { value: "never", label: "Sem expiração", days: null },
  { value: "1", label: "24 heures", days: 1 },
  { value: "7", label: "7 jours", days: 7 },
  { value: "30", label: "30 jours", days: 30 },
];

export function WhatsAppShare({ project, estimation, projectId, trigger }) {
  const [open, setOpen] = useState(false);
  const [phone, setPhone] = useState("");
  const [link, setLink] = useState("");
  const [expiresAt, setExpiresAt] = useState(null);
  const [expiryChoice, setExpiryChoice] = useState("never");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [stats, setStats] = useState(null);
  const [smsCfg, setSmsCfg] = useState({ twilio_enabled: false });

  const defaultMsg = useMemo(
    () => buildMessage({ project, estimation, link }),
    [project, estimation, link]
  );
  const displayMsg = message || defaultMsg;

  // Fetch existing share + SMS config when dialog opens
  useEffect(() => {
    if (!open || !projectId) return;
    api.get("/share/sms/config").then(({ data }) => setSmsCfg(data)).catch(() => {});
    api.get(`/projects/${projectId}/share/stats`).then(({ data }) => {
      setStats(data);
      if (data.url) setLink(data.url);
      if (data.expires_at) {
        setExpiresAt(data.expires_at);
        const days = Math.round((new Date(data.expires_at) - Date.now()) / 86400000);
        setExpiryChoice(String([1, 7, 30].find((d) => Math.abs(days - d) < 1) || "never"));
      }
    }).catch(() => {});
  }, [open, projectId]);

  const generateLink = async () => {
    if (!projectId) {
      toast.info("Guarde primeiro o projeto para uma ligação pública");
      return;
    }
    setBusy(true);
    try {
      const opt = EXPIRY_OPTIONS.find((o) => o.value === expiryChoice);
      const { data } = await api.post(`/projects/${projectId}/share`,
        opt?.days ? { expires_in_days: opt.days } : {});
      setLink(data.url);
      setExpiresAt(data.expires_at || null);
      setMessage("");
      const { data: s } = await api.get(`/projects/${projectId}/share/stats`);
      setStats(s);
      toast.success("Link de partilha pronto");
    } catch {
      toast.error("Impossível gerar o link");
    } finally {
      setBusy(false);
    }
  };

  const revokeLink = async () => {
    if (!projectId || !link) return;
    setBusy(true);
    try {
      await api.delete(`/projects/${projectId}/share`);
      setLink("");
      setExpiresAt(null);
      setStats(null);
      toast.success("Link revogado");
    } finally { setBusy(false); }
  };

  const sendWhatsApp = () => {
    const text = encodeURIComponent(displayMsg);
    const p = cleanPhone(phone);
    const url = p ? `https://wa.me/${p.replace("+", "")}?text=${text}`
                  : `https://wa.me/?text=${text}`;
    window.open(url, "_blank", "noopener");
    toast.success("WhatsApp ouvert");
  };

  const sendSmsNative = () => {
    const text = encodeURIComponent(displayMsg);
    const p = cleanPhone(phone);
    // sms: opens native app on mobile; on desktop, may prompt an SMS handler.
    window.open(`sms:${p}?body=${text}`, "_blank", "noopener");
    toast.success("Application SMS ouverte");
  };

  const sendSmsTwilio = async () => {
    if (!projectId) return toast.info("Guarde primeiro o projeto");
    const p = cleanPhone(phone);
    if (!p.startsWith("+")) return toast.error("Número obrigatório em formato internacional (+33…)");
    setBusy(true);
    try {
      const { data } = await api.post(`/projects/${projectId}/share/sms`,
        { to: p, message: displayMsg });
      toast.success(`SMS enviado (${data.status})`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Envio impossível");
    } finally { setBusy(false); }
  };

  const copyMsg = async () => {
    try { await navigator.clipboard.writeText(displayMsg); toast.success("Mensagem copiada"); }
    catch { toast.error("Cópia impossível"); }
  };
  const copyLink = async () => {
    if (!link) return;
    try { await navigator.clipboard.writeText(link); toast.success("Link copiado"); }
    catch { toast.error("Cópia impossível"); }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger || (
          <Button
            variant="outline" data-testid="whatsapp-share-btn"
            className="rounded-sm gap-2 border-emerald-500/50 text-emerald-600 hover:bg-emerald-500 hover:text-white"
          >
            <MessageCircle className="h-4 w-4" /> Partager
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="rounded-sm max-w-lg max-h-[90vh] overflow-y-auto" data-testid="whatsapp-share-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">Enviar a estimativa a um cliente</DialogTitle>
          <DialogDescription>WhatsApp ou SMS — com ligação de leitura apenas e analytics de abertura.</DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 mt-2">
          <div className="grid gap-2">
            <Label htmlFor="wa-phone">Número do cliente (opcional para WhatsApp)</Label>
            <Input
              id="wa-phone" value={phone} onChange={(e) => setPhone(e.target.value)}
              placeholder="+33 6 12 34 56 78"
              data-testid="whatsapp-phone-input" className="rounded-sm h-11 num"
            />
          </div>

          {projectId && (
            <div className="grid gap-2 border border-border p-3 rounded-sm bg-secondary/30">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <Label className="mb-0">Lien public</Label>
                <div className="flex items-center gap-2">
                  <Select value={expiryChoice} onValueChange={setExpiryChoice}>
                    <SelectTrigger className="rounded-sm h-8 text-xs w-[130px]" data-testid="share-expiry-select">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {EXPIRY_OPTIONS.map((o) => (
                        <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {link ? (
                    <>
                      <Button size="sm" variant="ghost" onClick={copyLink} className="rounded-sm gap-1 text-xs h-8">
                        <Copy className="h-3 w-3" /> Copier
                      </Button>
                      <Button size="sm" variant="ghost" onClick={revokeLink} disabled={busy} className="rounded-sm gap-1 text-xs h-8 text-destructive">
                        Revogar
                      </Button>
                    </>
                  ) : (
                    <Button size="sm" onClick={generateLink} disabled={busy} data-testid="whatsapp-generate-link" className="rounded-sm gap-1 text-xs h-8">
                      <LinkIcon className="h-3 w-3" /> {busy ? "…" : "Gerar"}
                    </Button>
                  )}
                </div>
              </div>

              {link && (
                <a href={link} target="_blank" rel="noreferrer" className="text-xs font-mono truncate text-primary hover:underline flex items-center gap-1" data-testid="whatsapp-share-link">
                  <ExternalLink className="h-3 w-3 shrink-0" /> {link}
                </a>
              )}

              {(stats?.opens > 0 || expiresAt) && (
                <div className="flex flex-wrap gap-2 mt-1" data-testid="share-analytics">
                  {stats?.opens != null && (
                    <Badge variant="outline" className="rounded-sm gap-1 num">
                      <Eye className="h-3 w-3" /> {stats.opens} ouverture{stats.opens > 1 ? "s" : ""}
                    </Badge>
                  )}
                  {stats?.last_open_at && (
                    <Badge variant="outline" className="rounded-sm gap-1 num text-xs">
                      Última: {new Date(stats.last_open_at).toLocaleString("fr-FR")}
                    </Badge>
                  )}
                  {expiresAt && (
                    <Badge variant="outline" className="rounded-sm gap-1 num text-xs border-amber-500/50 text-amber-500">
                      <Clock className="h-3 w-3" /> Expira a {new Date(expiresAt).toLocaleDateString("fr-FR")}
                    </Badge>
                  )}
                </div>
              )}
            </div>
          )}

          <div className="grid gap-2">
            <Label>Message</Label>
            <Textarea
              value={displayMsg} onChange={(e) => setMessage(e.target.value)}
              rows={7} data-testid="whatsapp-message"
              className="rounded-sm text-xs font-mono"
            />
            <div className="flex justify-end">
              <Button size="sm" variant="ghost" onClick={copyMsg} className="rounded-sm gap-1 text-xs h-7">
                <Copy className="h-3 w-3" /> Copiar a mensagem
              </Button>
            </div>
          </div>
        </div>

        <Tabs defaultValue="wa" className="mt-2">
          <TabsList className="w-full rounded-sm">
            <TabsTrigger value="wa" className="flex-1 rounded-sm gap-2" data-testid="tab-share-whatsapp">
              <MessageCircle className="h-3 w-3" /> WhatsApp
            </TabsTrigger>
            <TabsTrigger value="sms" className="flex-1 rounded-sm gap-2" data-testid="tab-share-sms">
              <Smartphone className="h-3 w-3" /> SMS
            </TabsTrigger>
          </TabsList>
          <TabsContent value="wa" className="mt-3">
            <Button onClick={sendWhatsApp} data-testid="whatsapp-send-btn"
                    className="w-full rounded-sm gap-2 bg-emerald-600 hover:bg-emerald-700 text-white">
              <MessageCircle className="h-4 w-4" /> Ouvrir WhatsApp
            </Button>
          </TabsContent>
          <TabsContent value="sms" className="mt-3 grid gap-2">
            <Button onClick={sendSmsNative} data-testid="sms-native-btn"
                    variant="outline" className="w-full rounded-sm gap-2">
              <Smartphone className="h-4 w-4" /> Abrir app SMS do telefone
            </Button>
            <Button onClick={sendSmsTwilio} disabled={!smsCfg.twilio_enabled || busy}
                    data-testid="sms-twilio-btn"
                    className="w-full rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
              <Send className="h-4 w-4" />
              {smsCfg.twilio_enabled ? "Enviar via Twilio (servidor)" : "Twilio não configurado"}
            </Button>
            {!smsCfg.twilio_enabled && (
              <p className="text-xs text-muted-foreground text-center">
                Ajoutez <span className="font-mono">TWILIO_AUTH_TOKEN</span> et <span className="font-mono">TWILIO_FROM_NUMBER</span> dans <span className="font-mono">.env</span> para ativar o envio por servidor.
              </p>
            )}
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

export default WhatsAppShare;
