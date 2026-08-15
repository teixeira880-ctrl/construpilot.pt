import { AlertTriangle, UserCircle } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useI18n } from "@/context/I18nContext";
import { ProfileForm } from "@/components/account/ProfileForm";
import { PasswordForm } from "@/components/account/PasswordForm";
import { DevicesList } from "@/components/account/DevicesList";
import { TwoFaCard } from "@/components/account/TwoFaCard";

export default function Account() {
  const { user } = useAuth();
  const { t } = useI18n();

  return (
    <div className="max-w-lg mx-auto px-5 py-10 space-y-6" data-testid="account-page">
      <header>
        <p className="overline flex items-center gap-2 text-primary">
          <UserCircle className="h-4 w-4" /> {t("account.over")}
        </p>
        <h1 className="font-display text-3xl font-extrabold">{user?.name}</h1>
        <p className="text-sm text-muted-foreground">{user?.email}</p>
      </header>

      {user?.must_change_password && (
        <div className="surface p-4 border border-amber-500/40 bg-amber-500/10 flex items-start gap-3"
             data-testid="temp-password-banner">
          <AlertTriangle className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-sm">{t("account.temp_title")}</p>
            <p className="text-xs text-muted-foreground">
              {t("account.temp_desc")}
            </p>
          </div>
        </div>
      )}

      <ProfileForm />
      <TwoFaCard />
      <PasswordForm />
      <DevicesList />
    </div>
  );
}
