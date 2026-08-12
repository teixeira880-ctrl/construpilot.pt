import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Users, Crown, Building2, Copy, LogOut, Trash2, UserPlus, Mail, Check,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader,
  DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import { SectionTitle } from "@/components/Bits";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export default function Team() {
  const { user } = useAuth();
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);

  // Create dialog
  const [openCreate, setOpenCreate] = useState(false);
  const [newName, setNewName] = useState("");
  // Join dialog
  const [openJoin, setOpenJoin] = useState(false);
  const [joinCode, setJoinCode] = useState("");
  // Invite dialog
  const [openInvite, setOpenInvite] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/organizations/me");
      setState(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { if (user) refresh(); }, [user]);

  if (!user) {
    return <div className="surface p-10 text-center">Connectez-vous pour gérer votre équipe.</div>;
  }

  const create = async () => {
    if (newName.trim().length < 2) return toast.error("Nom trop court");
    setBusy(true);
    try {
      await api.post("/organizations", { name: newName.trim() });
      toast.success("Organisation créée");
      setOpenCreate(false); setNewName("");
      await refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Création impossible");
    } finally { setBusy(false); }
  };

  const join = async () => {
    if (joinCode.trim().length < 4) return toast.error("Code invalide");
    setBusy(true);
    try {
      await api.post("/organizations/join", { code: joinCode.trim().toUpperCase() });
      toast.success("Équipe rejointe");
      setOpenJoin(false); setJoinCode("");
      await refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Impossible de rejoindre");
    } finally { setBusy(false); }
  };

  const leave = async () => {
    if (!window.confirm("Quitter cette organisation ? Vous perdrez l'accès au branding partagé.")) return;
    try {
      await api.post("/organizations/leave");
      toast.success("Vous avez quitté l'équipe");
      await refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Impossible de quitter");
    }
  };

  const removeMember = async (uid, name) => {
    if (!window.confirm(`Retirer ${name || uid} de l'équipe ?`)) return;
    try {
      await api.delete(`/organizations/members/${uid}`);
      toast.success("Membre retiré");
      await refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Suppression impossible");
    }
  };

  const invite = async () => {
    if (!/@/.test(inviteEmail)) return toast.error("Email invalide");
    setBusy(true);
    try {
      const { data } = await api.post("/organizations/invite",
        { email: inviteEmail.trim(), role: inviteRole });
      toast.success(data.email_status === "sent"
        ? `Invitation envoyée à ${inviteEmail}`
        : `Code communiqué : partagez-le manuellement`);
      setOpenInvite(false); setInviteEmail("");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Invitation impossible");
    } finally { setBusy(false); }
  };

  const copyCode = async () => {
    if (!state?.org_code) return;
    try {
      await navigator.clipboard.writeText(state.org_code);
      setCopied(true); setTimeout(() => setCopied(false), 1500);
      toast.success("Code copié");
    } catch { toast.error("Copie impossible"); }
  };

  if (loading) return <div className="surface p-10 text-center">Chargement…</div>;

  // Not in an org → create or join
  if (!state?.in_org) {
    return (
      <div className="grid gap-10">
        <SectionTitle over="ConstruPilot Équipe" title="Partagez votre identité pro entre collègues">
          Créez une organisation et invitez vos collaborateurs : ils utiliseront le même logo,
          les mêmes coordonnées et la même charte sur tous les PDF, sans reconfigurer.
        </SectionTitle>

        <div className="grid md:grid-cols-2 gap-6">
          <div className="surface p-8 grid gap-4" data-testid="team-create-card">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 grid place-items-center bg-primary/10 rounded-sm">
                <Building2 className="h-5 w-5 text-primary" />
              </div>
              <p className="font-display text-xl font-bold">Créer une organisation</p>
            </div>
            <p className="text-sm text-muted-foreground">
              Vous devenez propriétaire. Votre branding actuel est repris automatiquement.
            </p>
            <Dialog open={openCreate} onOpenChange={setOpenCreate}>
              <DialogTrigger asChild>
                <Button data-testid="team-create-btn"
                  className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                  <Building2 className="h-4 w-4" /> Créer mon équipe
                </Button>
              </DialogTrigger>
              <DialogContent className="rounded-sm">
                <DialogHeader>
                  <DialogTitle>Nouvelle organisation</DialogTitle>
                  <DialogDescription>Le nom qui apparaîtra pour vos membres.</DialogDescription>
                </DialogHeader>
                <div className="grid gap-2">
                  <Label>Nom de l'organisation</Label>
                  <Input value={newName} onChange={(e) => setNewName(e.target.value)}
                    maxLength={120} placeholder="BTP Construction SAS"
                    data-testid="team-create-name" className="rounded-sm h-11" />
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setOpenCreate(false)} className="rounded-sm">
                    Annuler
                  </Button>
                  <Button onClick={create} disabled={busy} data-testid="team-create-confirm"
                    className="rounded-sm hover:bg-orange-600 hover:text-white">
                    Créer
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>

          <div className="surface p-8 grid gap-4" data-testid="team-join-card">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 grid place-items-center bg-primary/10 rounded-sm">
                <UserPlus className="h-5 w-5 text-primary" />
              </div>
              <p className="font-display text-xl font-bold">Rejoindre une équipe</p>
            </div>
            <p className="text-sm text-muted-foreground">
              Saisissez le code d'invitation reçu par email ou communiqué par votre collègue.
            </p>
            <Dialog open={openJoin} onOpenChange={setOpenJoin}>
              <DialogTrigger asChild>
                <Button variant="outline" data-testid="team-join-btn" className="rounded-sm gap-2">
                  <UserPlus className="h-4 w-4" /> Saisir le code
                </Button>
              </DialogTrigger>
              <DialogContent className="rounded-sm">
                <DialogHeader>
                  <DialogTitle>Rejoindre une organisation</DialogTitle>
                  <DialogDescription>Format : 4 lettres - 4 chiffres (ex : ABCD-1234).</DialogDescription>
                </DialogHeader>
                <div className="grid gap-2">
                  <Label>Code d'invitation</Label>
                  <Input value={joinCode} onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
                    maxLength={16} placeholder="ABCD-1234"
                    data-testid="team-join-code" className="rounded-sm h-11 num tracking-widest" />
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setOpenJoin(false)} className="rounded-sm">
                    Annuler
                  </Button>
                  <Button onClick={join} disabled={busy} data-testid="team-join-confirm"
                    className="rounded-sm hover:bg-orange-600 hover:text-white">
                    Rejoindre
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </div>
      </div>
    );
  }

  // In an org
  const isAdmin = state.role === "owner" || state.role === "admin";
  return (
    <div className="grid gap-10">
      <SectionTitle over={`Organisation · ${state.role}`} title={state.name}>
        Votre équipe utilise une identité visuelle commune sur tous les exports PDF.
      </SectionTitle>

      <div className="grid md:grid-cols-3 gap-6">
        <div className="surface p-6 grid gap-3" data-testid="team-code-card">
          <div className="flex items-center gap-2">
            <Building2 className="h-5 w-5 text-primary" />
            <p className="overline">Code d'invitation</p>
          </div>
          <div className="flex items-center gap-2">
            <Badge className="rounded-sm bg-primary text-primary-foreground num tracking-widest text-lg py-2 px-4"
                   data-testid="team-code">
              {state.org_code}
            </Badge>
            <Button size="sm" variant="outline" onClick={copyCode} data-testid="team-copy-code"
                    className="rounded-sm gap-1">
              {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Partagez ce code à vos collègues, ou envoyez-leur une invitation email.
          </p>
        </div>

        <div className="surface p-6 grid gap-3">
          <div className="flex items-center gap-2">
            <Users className="h-5 w-5 text-primary" />
            <p className="overline">Membres</p>
          </div>
          <p className="num font-display text-3xl font-extrabold" data-testid="team-member-count">
            {state.member_count}
          </p>
        </div>

        <div className="surface p-6 grid gap-3">
          <div className="flex items-center gap-2">
            <Crown className="h-5 w-5 text-primary" />
            <p className="overline">Votre rôle</p>
          </div>
          <p className="font-display text-2xl font-bold capitalize">{state.role}</p>
          <div className="flex gap-2">
            {isAdmin && (
              <Dialog open={openInvite} onOpenChange={setOpenInvite}>
                <DialogTrigger asChild>
                  <Button size="sm" data-testid="team-invite-btn"
                          className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                    <Mail className="h-3 w-3" /> Inviter
                  </Button>
                </DialogTrigger>
                <DialogContent className="rounded-sm">
                  <DialogHeader>
                    <DialogTitle>Inviter un collègue</DialogTitle>
                    <DialogDescription>
                      L'invitation lui sera envoyée par email avec le code de l'équipe.
                    </DialogDescription>
                  </DialogHeader>
                  <div className="grid gap-2">
                    <Label>Email</Label>
                    <Input value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)}
                           placeholder="collegue@entreprise.fr" data-testid="team-invite-email"
                           className="rounded-sm h-11" />
                  </div>
                  <DialogFooter>
                    <Button variant="outline" onClick={() => setOpenInvite(false)} className="rounded-sm">
                      Annuler
                    </Button>
                    <Button onClick={invite} disabled={busy} data-testid="team-invite-send"
                            className="rounded-sm hover:bg-orange-600 hover:text-white">
                      Envoyer l'invitation
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            )}
            <Button size="sm" variant="outline" onClick={leave} data-testid="team-leave-btn"
                    className="rounded-sm gap-2 text-destructive">
              <LogOut className="h-3 w-3" /> Quitter
            </Button>
          </div>
        </div>
      </div>

      <div className="surface p-6" data-testid="team-members-list">
        <p className="overline mb-4">Membres de l'équipe</p>
        <div className="grid gap-2">
          {state.members?.map((m) => (
            <div key={m.user_id}
                 className="flex items-center justify-between border-b border-border py-2"
                 data-testid={`team-member-${m.user_id}`}>
              <div>
                <div className="font-bold flex items-center flex-wrap gap-2">
                  <span>{m.name || m.email}</span>
                  {m.org_role === "owner" && (
                    <Badge className="rounded-sm bg-primary/10 text-primary text-[10px]">
                      <Crown className="h-3 w-3 inline mr-1" /> Propriétaire
                    </Badge>
                  )}
                  {m.org_role === "admin" && (
                    <Badge variant="outline" className="rounded-sm text-[10px]">Admin</Badge>
                  )}
                </div>
                <p className="text-xs text-muted-foreground num">
                  {m.email}
                  {m.joined_org_at && ` · rejoint le ${new Date(m.joined_org_at).toLocaleDateString("fr-FR")}`}
                </p>
              </div>
              {isAdmin && m.org_role !== "owner" && m.user_id !== user.user_id && (
                <Button size="sm" variant="ghost" onClick={() => removeMember(m.user_id, m.name)}
                        data-testid={`team-remove-${m.user_id}`}
                        className="rounded-sm gap-1 text-destructive">
                  <Trash2 className="h-3 w-3" /> Retirer
                </Button>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
