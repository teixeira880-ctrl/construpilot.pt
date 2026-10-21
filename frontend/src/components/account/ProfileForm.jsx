import { useState, useRef } from "react";
import { toast } from "sonner";
import { UserCog, Save, Camera, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";

export const ProfileForm = () => {
  const { user, setUser } = useAuth();
  const [name, setName] = useState(user?.name || "");
  const [phone, setPhone] = useState(user?.phone || "");
  const [email, setEmail] = useState(user?.email || "");
  const [pwd, setPwd] = useState("");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);
  const isGoogle = user?.auth_provider === "google";
  const emailChanged = email.trim().toLowerCase() !== (user?.email || "");

  const onPhoto = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const img = new Image();
    img.onload = async () => {
      const canvas = document.createElement("canvas");
      const scale = Math.min(1, 256 / Math.max(img.width, img.height));
      canvas.width = Math.round(img.width * scale);
      canvas.height = Math.round(img.height * scale);
      canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
      try {
        const { data } = await api.post("/auth/profile-photo", {
          image_b64: canvas.toDataURL("image/jpeg", 0.85),
        });
        setUser(data.user);
        toast.success("Foto de perfil atualizada");
      } catch {
        toast.error("Impossível enviar a foto");
      }
      URL.revokeObjectURL(img.src);
    };
    img.src = URL.createObjectURL(file);
    e.target.value = "";
  };

  const removePhoto = async () => {
    try {
      const { data } = await api.delete("/auth/profile-photo");
      setUser(data.user);
      toast.success("Foto eliminada");
    } catch {
      toast.error("Não foi possível eliminar");
    }
  };

  const save = async (e) => {
    e.preventDefault();
    if (emailChanged && !pwd) {
      return toast.error("Palavra-passe atual obrigatória para alterar o email");
    }
    setBusy(true);
    try {
      const body = { name: name.trim(), phone: phone.trim() };
      if (emailChanged) {
        body.email = email.trim();
        body.current_password = pwd;
      }
      const { data } = await api.put("/auth/profile", body);
      setUser(data.user);
      setPwd("");
      toast.success("Perfil atualizado");
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Não foi possível atualizar");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={save} className="surface p-5 space-y-4" data-testid="profile-form">
      <p className="font-semibold flex items-center gap-2">
        <UserCog className="h-4 w-4 text-primary" /> As minhas informações
      </p>
      <div className="flex items-center gap-4" data-testid="profile-photo-section">
        {user?.picture ? (
          <img src={user.picture} alt="Foto de perfil" data-testid="profile-photo-preview"
               className="h-16 w-16 rounded-full object-cover border border-border" />
        ) : (
          <div className="h-16 w-16 rounded-full bg-muted flex items-center justify-center text-lg font-bold text-muted-foreground"
               data-testid="profile-photo-placeholder">
            {(user?.name || "?").charAt(0).toUpperCase()}
          </div>
        )}
        <div className="flex flex-col gap-1.5">
          <input ref={fileRef} type="file" accept="image/*" className="hidden"
                 onChange={onPhoto} data-testid="profile-photo-input" />
          <Button type="button" variant="outline" size="sm" className="rounded-sm gap-2"
                  onClick={() => fileRef.current?.click()} data-testid="profile-photo-upload-btn">
            <Camera className="h-3.5 w-3.5" /> {user?.picture ? "Alterar a foto" : "Adicionar uma foto"}
          </Button>
          {user?.picture && (
            <Button type="button" variant="ghost" size="sm" className="rounded-sm gap-2 text-muted-foreground"
                    onClick={removePhoto} data-testid="profile-photo-remove-btn">
              <Trash2 className="h-3.5 w-3.5" /> Eliminar
            </Button>
          )}
        </div>
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="pf-name" className="text-xs">Nome completo</Label>
        <Input id="pf-name" value={name} required minLength={2} maxLength={80}
               onChange={(e) => setName(e.target.value)}
               data-testid="profile-name-input" className="rounded-sm" />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="pf-phone" className="text-xs">Telefone</Label>
        <Input id="pf-phone" type="tel" value={phone} maxLength={20}
               placeholder="+33 6 12 34 56 78"
               onChange={(e) => setPhone(e.target.value)}
               data-testid="profile-phone-input" className="rounded-sm" />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="pf-email" className="text-xs">Email de ligação</Label>
        <Input id="pf-email" type="email" value={email} required disabled={isGoogle}
               onChange={(e) => setEmail(e.target.value)}
               data-testid="profile-email-input" className="rounded-sm" />
        {isGoogle && (
          <p className="text-[10px] text-muted-foreground">
            Conta ligada via Google — o e-mail não pode ser alterado.
          </p>
        )}
      </div>
      {emailChanged && !isGoogle && (
        <div className="grid gap-1.5">
          <Label htmlFor="pf-pwd" className="text-xs">
            Palavra-passe atual (necessária para alterar o e-mail)
          </Label>
          <Input id="pf-pwd" type="password" value={pwd} required
                 onChange={(e) => setPwd(e.target.value)}
                 data-testid="profile-current-password-input" className="rounded-sm" />
        </div>
      )}
      <Button type="submit" disabled={busy} className="rounded-sm w-full gap-2"
              data-testid="profile-save-btn">
        <Save className="h-4 w-4" /> {busy ? "…" : "Guardar as minhas informações"}
      </Button>
    </form>
  );
};
