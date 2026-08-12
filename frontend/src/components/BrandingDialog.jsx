import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Building2, Upload, Trash2, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";

/** Dialog de configuration du branding pro (logo + société + contact)
 *  utilisé dans le PDF Métré. */
export function BrandingDialog({ trigger }) {
  const [open, setOpen] = useState(false);
  const [companyName, setCompanyName] = useState("");
  const [contactLine, setContactLine] = useState("");
  const [logoB64, setLogoB64] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    api.get("/users/me/branding").then(({ data }) => {
      setCompanyName(data.company_name || "");
      setContactLine(data.contact_line || "");
      setLogoB64(data.logo_b64 || "");
    });
  }, [open]);

  const onLogoChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 400 * 1024) return toast.error("Logo trop volumineux (max 400 Ko)");
    const reader = new FileReader();
    reader.onload = () => setLogoB64(reader.result);
    reader.readAsDataURL(file);
  };

  const save = async () => {
    setBusy(true);
    try {
      await api.put("/users/me/branding", {
        company_name: companyName, contact_line: contactLine, logo_b64: logoB64 || null,
      });
      toast.success("Identité pro enregistrée");
      setOpen(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Sauvegarde impossible");
    } finally { setBusy(false); }
  };

  const removeLogo = () => setLogoB64("");

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger || (
          <Button variant="outline" size="sm" data-testid="branding-open-btn" className="rounded-sm gap-2">
            <Building2 className="h-4 w-4" /> Identité pro
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="rounded-sm max-w-lg" data-testid="branding-dialog">
        <DialogHeader>
          <DialogTitle>Personnaliser le PDF Métré</DialogTitle>
          <DialogDescription>
            Ajoutez votre logo et vos coordonnées — ils apparaîtront en tête de chaque PDF que vous exportez.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label>Nom de la société</Label>
            <Input value={companyName} onChange={(e) => setCompanyName(e.target.value)}
                   placeholder="Ex : BTP Construction SAS"
                   data-testid="branding-company-input"
                   className="rounded-sm h-11" maxLength={120} />
          </div>
          <div className="grid gap-2">
            <Label>Ligne contact</Label>
            <Textarea value={contactLine} onChange={(e) => setContactLine(e.target.value)}
                      placeholder="12 rue de la Paix · 75002 Paris · 01 23 45 67 89 · contact@…"
                      data-testid="branding-contact-input"
                      className="rounded-sm text-sm" rows={2} maxLength={200} />
          </div>
          <div className="grid gap-2">
            <Label>Logo (PNG/JPG, max 400 Ko)</Label>
            {logoB64 ? (
              <div className="flex items-center gap-3 border border-border rounded-sm p-3 bg-secondary/30">
                <img src={logoB64.startsWith("data:") ? logoB64 : `data:image/png;base64,${logoB64}`}
                     alt="Logo" className="h-16 w-16 object-contain" data-testid="branding-logo-preview" />
                <Button size="sm" variant="ghost" onClick={removeLogo} data-testid="branding-logo-remove"
                        className="rounded-sm gap-1 ml-auto text-destructive">
                  <Trash2 className="h-3 w-3" /> Retirer
                </Button>
              </div>
            ) : (
              <label className="border border-dashed border-border rounded-sm p-4 text-center cursor-pointer hover:border-primary">
                <Upload className="h-5 w-5 mx-auto text-muted-foreground" />
                <p className="text-xs text-muted-foreground mt-1">Cliquez pour importer un logo</p>
                <input type="file" accept="image/png,image/jpeg" onChange={onLogoChange}
                       data-testid="branding-logo-input" className="sr-only" />
              </label>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)} className="rounded-sm">Annuler</Button>
          <Button onClick={save} disabled={busy} data-testid="branding-save-btn"
                  className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
            <Save className="h-4 w-4" /> Enregistrer
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default BrandingDialog;
