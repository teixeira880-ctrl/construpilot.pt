import { useState } from "react";
import { Button } from "@/components/ui/button";
import { MODES, useWorkProfile } from "@/lib/workProfile";
import { WorkProfileOnboarding } from "@/components/workprofile/WorkProfileOnboarding";

/** Resumo editável do perfil de trabalho (Preferências). Não altera permissões nem plano. */
export function WorkProfileSettings() {
  const { profile, save } = useWorkProfile();
  const [open, setOpen] = useState(false);
  const mode = MODES.find(m => m.key === profile.mode);
  return (
    <section className="rounded-2xl border bg-card p-4 sm:p-5" data-testid="work-profile-settings">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Perfil de trabalho</h2>
          <p className="text-sm text-muted-foreground">
            Modo: <strong>{mode?.label}</strong> · Linguagem: <strong>{profile.language === "tecnica" ? "técnica" : "corrente"}</strong>
            {profile.professions?.length ? ` · ${profile.professions.length} profissão(ões) escolhida(s)` : " · sem profissão indicada"}
          </p>
          <p className="text-xs text-muted-foreground">Só muda as sugestões e a forma de apresentar. As suas permissões e o seu plano não mudam.</p>
        </div>
        <Button type="button" variant="outline" onClick={() => setOpen(true)} data-testid="work-profile-settings-edit">Alterar</Button>
      </div>
      <WorkProfileOnboarding open={open} onOpenChange={setOpen} profile={profile} onSave={save} />
    </section>
  );
}
