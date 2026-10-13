import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Building2, Upload, Trash2, Save, Award, MapPin, Landmark } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";

const CERTS = [
  ["qualibat", "Qualibat"], ["rge", "RGE"], ["qualipac", "QualiPAC"],
  ["qualifelec", "Qualifelec"], ["qualibois", "Qualibois"],
];

/** Dialog de configuration du branding pro (logo + société + contact + certifications)
 *  utilisé dans les PDF Métré / Devis / Factures. */
export function BrandingDialog({ trigger, onSaved, contentClassName = "", overlayClassName }) {
  const [open, setOpen] = useState(false);
  const [companyName, setCompanyName] = useState("");
  const [companyEmail, setCompanyEmail] = useState("");
  const [contactLine, setContactLine] = useState("");
  const [siret, setSiret] = useState("");
  const [vat, setVat] = useState("");
  const [nif, setNif] = useState("");
  const [alvara, setAlvara] = useState("");
  const [address, setAddress] = useState("");
  const [city, setCity] = useState("");
  const [postalCode, setPostalCode] = useState("");
  const [country, setCountry] = useState("FR");
  const [logoB64, setLogoB64] = useState("");
  const [defaultEmailMsg, setDefaultEmailMsg] = useState("");
  const [serviceZones, setServiceZones] = useState("");
  const [bankDetails, setBankDetails] = useState("");
  const [certSel, setCertSel] = useState({});
  const [busy, setBusy] = useState(false);
  const [source, setSource] = useState("user");
  const [orgName, setOrgName] = useState("");
  const [canEdit, setCanEdit] = useState(true);

  useEffect(() => {
    if (!open) return;
    api.get("/users/me/branding").then(({ data }) => {
      setCompanyName(data.company_name || "");
      setCompanyEmail(data.company_email || "");
      setContactLine(data.contact_line || "");
      setSiret(data.siret || "");
      setVat(data.vat || "");
      setNif(data.nif || "");
      setAlvara(data.alvara || "");
      setAddress(data.address || "");
      setCity(data.city || "");
      setPostalCode(data.postal_code || "");
      setCountry(data.country || "FR");
      setLogoB64(data.logo_b64 || "");
      setDefaultEmailMsg(data.default_email_message || "");
      setServiceZones((data.service_zones || []).join(", "));
      setBankDetails(data.bank_details || "");
      const map = {};
      (data.certifications || []).forEach((c) => { map[c.code] = c.number || ""; });
      setCertSel(map);
      setSource(data.source || "user");
      setOrgName(data.org_name || "");
      setCanEdit(data.can_edit !== false);
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

  const toggleCert = (code) => setCertSel((s) => {
    const n = { ...s };
    if (code in n) delete n[code]; else n[code] = "";
    return n;
  });

  const save = async () => {
    setBusy(true);
    try {
      await api.put("/users/me/branding", {
        company_name: companyName, company_email: companyEmail, contact_line: contactLine, logo_b64: logoB64 || null,
        siret: siret, vat: vat, nif: nif, alvara: alvara,
        address: address, city: city, postal_code: postalCode, country: country,
        default_email_message: defaultEmailMsg,
        service_zones: serviceZones.split(",").map((s) => s.trim()).filter(Boolean),
        bank_details: bankDetails,
        certifications: Object.entries(certSel).map(([code, number]) => ({ code, number })),
      });
      toast.success("Identidade profissional guardada");
      setOpen(false);
      onSaved?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Não foi possível guardar");
    } finally { setBusy(false); }
  };

  const removeLogo = () => setLogoB64("");

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger || (
          <Button variant="outline" size="sm" data-testid="branding-open-btn" className="rounded-sm gap-2">
            <Building2 className="h-4 w-4" /> Identidade profissional
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className={`rounded-sm max-w-lg max-h-[88vh] overflow-y-auto ${contentClassName}`} overlayClassName={overlayClassName} data-testid="branding-dialog">
        <DialogHeader>
          <DialogTitle>Identidade profissional & certificações</DialogTitle>
          <DialogDescription>
            {source === "organization"
              ? <>Identidade partilhada com a equipa <b>{orgName}</b>. {canEdit
                  ? "As suas modificações aplicam-se a todos os membros."
                  : "Apenas um admin ou o proprietário pode modificar estas informações."}</>
              : "Logótipo, contactos e certificações — exibidos no cabeçalho de cada PDF (medições, orçamento, faturas)."}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label>Nome da sociedade</Label>
            <Input value={companyName} onChange={(e) => setCompanyName(e.target.value)}
                   placeholder="Ex : BTP Construction SAS" disabled={!canEdit}
                   data-testid="branding-company-input"
                   className="rounded-sm h-11" maxLength={120} />
          </div>
          <div className="grid gap-2">
            <Label>E-mail oficial da empresa</Label>
            <Input type="email" value={companyEmail} onChange={(e) => setCompanyEmail(e.target.value)}
                   placeholder="Ex: contacto@a-sua-empresa.pt" disabled={!canEdit}
                   data-testid="branding-company-email-input"
                   className="rounded-sm h-11" maxLength={120} />
            <p className="text-xs text-muted-foreground">
              Usado como endereço de resposta (reply-to): quando um cliente responde a um orçamento/fatura, a sua resposta chega a esta caixa.
            </p>
          </div>
          <div className="grid gap-2">
            <Label>Ligne contact</Label>
            <Textarea value={contactLine} onChange={(e) => setContactLine(e.target.value)}
                      placeholder="12 rue de la Paix · 75002 Paris · 01 23 45 67 89 · contact@…"
                      disabled={!canEdit}
                      data-testid="branding-contact-input"
                      className="rounded-sm text-sm" rows={2} maxLength={200} />
          </div>

          {country === "PT" ? (
            <>
              <div className="grid grid-cols-2 gap-3">
                <div className="grid gap-2">
                  <Label>NIF</Label>
                  <Input value={nif} onChange={(e) => setNif(e.target.value)}
                         placeholder="9 dígitos" disabled={!canEdit}
                         data-testid="branding-nif-input" className="rounded-sm h-11 num" maxLength={9} />
                </div>
                <div className="grid gap-2">
                  <Label>N.º de IVA</Label>
                  <Input value={vat} onChange={(e) => setVat(e.target.value)}
                         placeholder="PT123456789" disabled={!canEdit}
                         data-testid="branding-vat-input" className="rounded-sm h-11 num" maxLength={20} />
                </div>
              </div>
              <div className="grid gap-2">
                <Label>Alvará / Certidão (opcional)</Label>
                <Input value={alvara} onChange={(e) => setAlvara(e.target.value)}
                       placeholder="Alvará IMPIC ou Certidão Permanente" disabled={!canEdit}
                       data-testid="branding-alvara-input" className="rounded-sm h-11" maxLength={40} />
              </div>
              <p className="text-[11px] text-muted-foreground">Apresentado no cabeçalho dos seus orçamentos e faturas para clientes em Portugal.</p>
            </>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3">
                <div className="grid gap-2">
                  <Label>SIRET</Label>
                  <Input value={siret} onChange={(e) => setSiret(e.target.value)}
                         placeholder="14 chiffres" disabled={!canEdit}
                         data-testid="branding-siret-input" className="rounded-sm h-11 num" maxLength={14} />
                </div>
                <div className="grid gap-2">
                  <Label>TVA intracom.</Label>
                  <Input value={vat} onChange={(e) => setVat(e.target.value)}
                         placeholder="FR12345678901" disabled={!canEdit}
                         data-testid="branding-vat-input" className="rounded-sm h-11 num" maxLength={20} />
                </div>
              </div>
              <p className="text-[11px] text-muted-foreground">Obrigatório para faturas eletrónicas Factur-X 100% conformes.</p>
            </>
          )}

          <div className="grid gap-2">
            <Label>Adresse (rue)</Label>
            <Input value={address} onChange={(e) => setAddress(e.target.value)}
                   placeholder="12 rue de la Paix" disabled={!canEdit}
                   data-testid="branding-address-input" className="rounded-sm h-11" maxLength={160} />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="grid gap-2">
              <Label>Code postal</Label>
              <Input value={postalCode} onChange={(e) => setPostalCode(e.target.value)}
                     placeholder="75002" disabled={!canEdit}
                     data-testid="branding-postal-input" className="rounded-sm h-11 num" maxLength={12} />
            </div>
            <div className="grid gap-2">
              <Label>Ville</Label>
              <Input value={city} onChange={(e) => setCity(e.target.value)}
                     placeholder="Paris" disabled={!canEdit}
                     data-testid="branding-city-input" className="rounded-sm h-11" maxLength={80} />
            </div>
            <div className="grid gap-2">
              <Label>Pays</Label>
              <Input value={country} onChange={(e) => setCountry(e.target.value.toUpperCase())}
                     placeholder="FR" disabled={!canEdit}
                     data-testid="branding-country-input" className="rounded-sm h-11 num" maxLength={2} />
            </div>
          </div>


          <div className="grid gap-2">
            <Label className="flex items-center gap-1"><MapPin className="h-3.5 w-3.5 text-primary" /> Zones d'intervention</Label>
            <p className="text-[11px] text-muted-foreground -mt-1">
              Cidades ou distritos abrangidos, separados por vírgulas. Serve para lhe atribuir automaticamente os pedidos da sua área.
            </p>
            <Input value={serviceZones} onChange={(e) => setServiceZones(e.target.value)}
                   placeholder="Paris, Lyon, Rhône, 69, Villeurbanne" disabled={!canEdit}
                   data-testid="branding-zones-input" className="rounded-sm h-11" maxLength={600} />
          </div>


          <div className="grid gap-2">
            <Label className="flex items-center gap-1"><Landmark className="h-3.5 w-3.5 text-primary" /> Coordenadas bancárias (NIB)</Label>
            <p className="text-[11px] text-muted-foreground -mt-1">
              IBAN, BIC e banco. Exibidos apenas nas suas faturas para facilitar o pagamento.
            </p>
            <textarea value={bankDetails} onChange={(e) => setBankDetails(e.target.value)}
                      placeholder={"IBAN : FR76 3000 4000 0512 3456 7890 143\nBIC : BNPAFRPPXXX\nBanque : BNP Paribas"}
                      disabled={!canEdit} rows={3} maxLength={600}
                      data-testid="branding-bank-input"
                      className="rounded-sm border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary resize-y" />
          </div>


          <div className="grid gap-2">
            <Label className="flex items-center gap-1"><Award className="h-3.5 w-3.5 text-primary" /> Certifications</Label>
            <p className="text-[11px] text-muted-foreground -mt-1">
              Selecione as suas qualificações e indique o seu n.º de certificado (opcional).
            </p>
            <div className="grid gap-2" data-testid="branding-certs">
              {CERTS.map(([code, label]) => {
                const on = code in certSel;
                return (
                  <div key={code} className="flex items-center gap-2">
                    <button type="button" onClick={() => canEdit && toggleCert(code)}
                            disabled={!canEdit} data-testid={`cert-toggle-${code}`}
                            className={`h-8 px-3 rounded-sm text-xs font-bold border transition min-w-[110px] ${on ? "bg-primary text-primary-foreground border-primary" : "border-border text-muted-foreground hover:border-primary"}`}>
                      {label}
                    </button>
                    {on && (
                      <Input value={certSel[code]} disabled={!canEdit}
                             onChange={(e) => setCertSel((s) => ({ ...s, [code]: e.target.value }))}
                             placeholder="N° de certificado (opcional)"
                             className="rounded-sm h-8 text-xs flex-1" data-testid={`cert-number-${code}`} />
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="grid gap-2">
            <Label>Mensagem de acompanhamento predefinida (e-mails orçamento/faturas)</Label>
            <Textarea value={defaultEmailMsg} onChange={(e) => setDefaultEmailMsg(e.target.value)}
                      placeholder={"Olá {client}, Junto enviamos o seu orçamento n.º {numero}... Com os melhores cumprimentos, {entreprise}"}
                      disabled={!canEdit}
                      data-testid="branding-default-msg-input"
                      className="rounded-sm text-sm" rows={5} maxLength={1500} />
            <p className="text-[11px] text-muted-foreground">
              Reutilizado automaticamente em cada envio. Variáveis: <b>{"{client}"}</b>, <b>{"{entreprise}"}</b>, <b>{"{numero}"}</b>. Laissez vide pour le message type automatique.
            </p>
          </div>

          <div className="grid gap-2">
            <Label>Logo (PNG/JPG, max 400 Ko)</Label>
            {logoB64 ? (
              <div className="flex items-center gap-3 border border-border rounded-sm p-3 bg-secondary/30">
                <img src={logoB64.startsWith("data:") ? logoB64 : `data:image/png;base64,${logoB64}`}
                     alt="Logo" className="h-16 w-16 object-contain" data-testid="branding-logo-preview" />
                {canEdit && (
                  <Button size="sm" variant="ghost" onClick={removeLogo} data-testid="branding-logo-remove"
                          className="rounded-sm gap-1 ml-auto text-destructive">
                    <Trash2 className="h-3 w-3" /> Retirer
                  </Button>
                )}
              </div>
            ) : canEdit ? (
              <label className="border border-dashed border-border rounded-sm p-4 text-center cursor-pointer hover:border-primary">
                <Upload className="h-5 w-5 mx-auto text-muted-foreground" />
                <p className="text-xs text-muted-foreground mt-1">Clique para importar um logótipo</p>
                <input type="file" accept="image/png,image/jpeg" onChange={onLogoChange}
                       data-testid="branding-logo-input" className="sr-only" />
              </label>
            ) : (
              <p className="text-xs text-muted-foreground">Nenhum logótipo definido.</p>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)} className="rounded-sm">
            {canEdit ? "Cancelar" : "Fechar"}
          </Button>
          {canEdit && (
            <Button onClick={save} disabled={busy} data-testid="branding-save-btn"
                    className="rounded-sm gap-2">
              <Save className="h-4 w-4" /> Guardar
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default BrandingDialog;
