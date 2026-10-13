import { useState } from "react";
import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { deckFileUrl } from "@/lib/pitchDeck";

const EMPTY_FORM = { name: "", email: "", fund: "", note: "" };

export const DeckDownloadDialog = ({ open, onOpenChange, format }) => {
  const [form, setForm] = useState(EMPTY_FORM);
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const set = (key) => (e) => setForm((prev) => ({ ...prev, [key]: e.target.value }));
  const label = format === "pptx" ? "PowerPoint" : "PDF";
  const url = deckFileUrl(format);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.email || busy) return;
    setBusy(true);
    // Open synchronously with the user's click, not after an awaited API call.
    // The explicit link below also works when a browser blocks popups.
    window.open(url, "_blank", "noopener,noreferrer");
    setReady(true);
    try { await api.post("/investors/deck-request", form); }
    catch { /* Preserve the existing public download if lead logging fails. */ }
    finally { setBusy(false); }
  };

  const changeOpen = (value) => {
    if (!value) { setReady(false); setForm(EMPTY_FORM); }
    onOpenChange(value);
  };

  return (
    <Dialog open={open} onOpenChange={changeOpen}>
      <DialogContent data-testid="deck-download-dialog">
        <DialogHeader>
          <DialogTitle data-testid="deck-download-title">Recevoir le pitch deck</DialogTitle>
          <DialogDescription data-testid="deck-download-description">{label} — ConstruPilot</DialogDescription>
        </DialogHeader>
        {ready ? (
          <div className="grid gap-4">
            <p role="status" data-testid="deck-download-ready">Votre fichier est prêt.</p>
            <Button asChild className="gap-2" data-testid="deck-download-file-link">
              <a href={url} target="_blank" rel="noopener noreferrer"><Download className="h-4 w-4" />Télécharger le {label}</a>
            </Button>
            <Button variant="outline" data-testid="deck-download-close" onClick={() => changeOpen(false)}>Fermer</Button>
          </div>
        ) : (
          <form onSubmit={submit} className="grid gap-4" data-testid="deck-download-form">
            <div className="grid gap-1.5">
              <Label htmlFor="deck-name">Nom</Label>
              <Input id="deck-name" value={form.name} onChange={set("name")} placeholder="Votre nom" data-testid="deck-form-name" />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="deck-email">E-mail *</Label>
              <Input id="deck-email" type="email" required value={form.email} onChange={set("email")} placeholder="vous@fonds.com" data-testid="deck-form-email" />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="deck-fund">Fonds / société</Label>
              <Input id="deck-fund" value={form.fund} onChange={set("fund")} placeholder="Ex : Urban Ventures" data-testid="deck-form-fund" />
            </div>
            <DialogFooter>
              <Button type="submit" disabled={busy} className="rounded-full gap-2" data-testid="deck-form-submit"><Download className="h-4 w-4" />{busy ? "…" : `Télécharger le ${label}`}</Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
};