import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Users, Crown, Building2, Copy, LogOut, Trash2, UserPlus, Mail, Check, ArrowRightLeft,
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
    return <div className="surface p-10 text-center">Ligue-se para gerir a sua equipa.</div>;
  }

  const create = async () => {
    if (newName.trim().length < 2) return toast.error("Nome demasiado curto");
    setBusy(true);
    try {
      await api.post("/organizations", { name: newName.trim() });
      toast.success("Organização criada");
      setOpenCreate(false); setNewName("");
      await refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Criação impossível");
    } finally { setBusy(false); }
  };

  const join = async () => {
    if (joinCode.trim().length < 4) return toast.error("Código inválido");
    setBusy(true);
    try {
      await api.post("/organizations/join", { code: joinCode.trim().toUpperCase() });
      toast.success("Equipa aderida");
      setOpenJoin(false); setJoinCode("");
      await refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Impossível aderir");
    } finally { setBusy(false); }
  };

  const leave = async () => {
    if (!window.confirm("Sair desta organização? Perderá o acesso ao branding partilhado.")) return;
    try {
      await api.post("/organizations/leave");
      toast.success("Saiu da equipa");
      await refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Impossível sair");
    }
  };

  const removeMember = async (uid, name) => {
    if (!window.confirm(`Remover ${name || uid} da equipa?`)) return;
    try {
      await api.delete(`/organizations/members/${uid}`);
      toast.success("Membro removido");
      await refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Não foi possível eliminar");
    }
  };

  const transferOwnership = async (uid, name) => {
    if (!window.confirm(
      `Transferir a propriedade da equipa para ${name || uid} ?\n\n` +
      `Passará a admin. Esta ação só é reversível se o novo proprietário lhe voltar a transferir a propriedade.`
    )) return;
    try {
      await api.post("/organizations/transfer-ownership", { new_owner_user_id: uid });
      toast.success(`Propriedade transferida para ${name}`);
      await refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Transferência impossível");
    }
  };

  const invite = async () => {
    if (!/@/.test(inviteEmail)) return toast.error("E-mail inválido");
    setBusy(true);
    try {
      const { data } = await api.post("/organizations/invite",
        { email: inviteEmail.trim(), role: inviteRole });
      toast.success(data.email_status === "sent"
        ? `Convite enviado para ${inviteEmail}`
        : `Código comunicado: partilhe-o manualmente`);
      setOpenInvite(false); setInviteEmail("");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Convite impossível");
    } finally { setBusy(false); }
  };

  const copyCode = async () => {
    if (!state?.org_code) return;
    try {
      await navigator.clipboard.writeText(state.org_code);
      setCopied(true); setTimeout(() => setCopied(false), 1500);
      toast.success("Código copiado");
    } catch { toast.error("Cópia impossível"); }
  };

  if (loading) return <div className="surface p-10 text-center">A carregar…</div>;

  // Not in an org → create or join
  if (!state?.in_org) {
    return (
      <div className="grid gap-10">
        <SectionTitle over="ConstruPilot Equipa" title="Partilhe a sua identidade profissional entre colegas">
          Crie uma organização e convide os seus colaboradores: eles utilizarão o mesmo logótipo, os mesmos contactos e a mesma identidade em todos os PDF, sem reconfigurar.
        </SectionTitle>

        <div className="grid md:grid-cols-2 gap-6">
          <div className="surface p-8 grid gap-4" data-testid="team-create-card">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 grid place-items-center bg-primary/10 rounded-sm">
                <Building2 className="h-5 w-5 text-primary" />
              </div>
              <p className="font-display text-xl font-bold">Criar uma organização</p>
            </div>
            <p className="text-sm text-muted-foreground">
              Torna-se proprietário. A sua imagem atual é retomada automaticamente.
            </p>
            <Dialog open={openCreate} onOpenChange={setOpenCreate}>
              <DialogTrigger asChild>
                <Button data-testid="team-create-btn"
                  className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                  <Building2 className="h-4 w-4" /> Criar a minha equipa
                </Button>
              </DialogTrigger>
              <DialogContent className="rounded-sm">
                <DialogHeader>
                  <DialogTitle>Nova organização</DialogTitle>
                  <DialogDescription>O nome que aparecerá para os seus membros.</DialogDescription>
                </DialogHeader>
                <div className="grid gap-2">
                  <Label>Nome da organização</Label>
                  <Input value={newName} onChange={(e) => setNewName(e.target.value)}
                    maxLength={120} placeholder="BTP Construction SAS"
                    data-testid="team-create-name" className="rounded-sm h-11" />
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setOpenCreate(false)} className="rounded-sm">
                    Cancelar
                  </Button>
                  <Button onClick={create} disabled={busy} data-testid="team-create-confirm"
                    className="rounded-sm hover:bg-orange-600 hover:text-white">
                    Criar
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
              <p className="font-display text-xl font-bold">Juntar-se a uma equipa</p>
            </div>
            <p className="text-sm text-muted-foreground">
              Insira o código de convite recebido por email ou comunicado pelo seu colega.
            </p>
            <Dialog open={openJoin} onOpenChange={setOpenJoin}>
              <DialogTrigger asChild>
                <Button variant="outline" data-testid="team-join-btn" className="rounded-sm gap-2">
                  <UserPlus className="h-4 w-4" /> Inserir o código
                </Button>
              </DialogTrigger>
              <DialogContent className="rounded-sm">
                <DialogHeader>
                  <DialogTitle>Aderir a uma organização</DialogTitle>
                  <DialogDescription>Formato: 4 letras - 4 algarismos (ex.: ABCD-1234).</DialogDescription>
                </DialogHeader>
                <div className="grid gap-2">
                  <Label>Código de convite</Label>
                  <Input value={joinCode} onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
                    maxLength={16} placeholder="ABCD-1234"
                    data-testid="team-join-code" className="rounded-sm h-11 num tracking-widest" />
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setOpenJoin(false)} className="rounded-sm">
                    Cancelar
                  </Button>
                  <Button onClick={join} disabled={busy} data-testid="team-join-confirm"
                    className="rounded-sm hover:bg-orange-600 hover:text-white">
                    Aderir
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
      <SectionTitle over={`Organização · ${state.role}`} title={state.name}>
        A sua equipa utiliza uma identidade visual comum em todas as exportações PDF.
      </SectionTitle>

      <div className="grid md:grid-cols-3 gap-6">
        <div className="surface p-6 grid gap-3" data-testid="team-code-card">
          <div className="flex items-center gap-2">
            <Building2 className="h-5 w-5 text-primary" />
            <p className="overline">Código de convite</p>
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
            Partilhe este código com os seus colegas, ou envie-lhes um convite por email.
          </p>
        </div>

        <div className="surface p-6 grid gap-3">
          <div className="flex items-center gap-2">
            <Users className="h-5 w-5 text-primary" />
            <p className="overline">Membros</p>
          </div>
          <p className="num font-display text-3xl font-extrabold" data-testid="team-member-count">
            {state.member_count}
          </p>
        </div>

        <div className="surface p-6 grid gap-3">
          <div className="flex items-center gap-2">
            <Crown className="h-5 w-5 text-primary" />
            <p className="overline">A sua função</p>
          </div>
          <p className="font-display text-2xl font-bold capitalize">{state.role}</p>
          <div className="flex gap-2">
            {isAdmin && (
              <Dialog open={openInvite} onOpenChange={setOpenInvite}>
                <DialogTrigger asChild>
                  <Button size="sm" data-testid="team-invite-btn"
                          className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                    <Mail className="h-3 w-3" /> Convidar
                  </Button>
                </DialogTrigger>
                <DialogContent className="rounded-sm">
                  <DialogHeader>
                    <DialogTitle>Convidar um colega</DialogTitle>
                    <DialogDescription>
                      O convite será enviado por email com o código da equipa.
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
                      Cancelar
                    </Button>
                    <Button onClick={invite} disabled={busy} data-testid="team-invite-send"
                            className="rounded-sm hover:bg-orange-600 hover:text-white">
                      Enviar o convite
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            )}
            <Button size="sm" variant="outline" onClick={leave} data-testid="team-leave-btn"
                    className="rounded-sm gap-2 text-destructive">
              <LogOut className="h-3 w-3" /> Sair
            </Button>
          </div>
        </div>
      </div>

      <div className="surface p-6" data-testid="team-members-list">
        <p className="overline mb-4">Membros da equipa</p>
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
                      <Crown className="h-3 w-3 inline mr-1" /> Proprietário
                    </Badge>
                  )}
                  {m.org_role === "admin" && (
                    <Badge variant="outline" className="rounded-sm text-[10px]">Admin</Badge>
                  )}
                </div>
                <p className="text-xs text-muted-foreground num">
                  {m.email}
                  {m.joined_org_at && ` · aderiu em ${new Date(m.joined_org_at).toLocaleDateString("pt-PT")}`}
                </p>
              </div>
              {isAdmin && m.org_role !== "owner" && m.user_id !== user.user_id && (
                <div className="flex gap-1 shrink-0">
                  {state.role === "owner" && (
                    <Button size="sm" variant="ghost"
                            onClick={() => transferOwnership(m.user_id, m.name || m.email)}
                            data-testid={`team-transfer-${m.user_id}`}
                            className="rounded-sm gap-1 text-primary">
                      <ArrowRightLeft className="h-3 w-3" /> Transferir
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" onClick={() => removeMember(m.user_id, m.name)}
                          data-testid={`team-remove-${m.user_id}`}
                          className="rounded-sm gap-1 text-destructive">
                    <Trash2 className="h-3 w-3" /> Remover
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
