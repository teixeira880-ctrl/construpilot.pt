import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CheckCircle2, XCircle, Loader2 } from "lucide-react";

export default function VerifyEmail() {
  const { token } = useParams();
  const nav = useNavigate();
  const [state, setState] = useState("loading"); // loading | ok | error

  useEffect(() => {
    api.get(`/auth/verify-email/${token}`)
      .then(() => setState("ok"))
      .catch(() => setState("error"));
  }, [token]);

  return (
    <div className="min-h-[70vh] grid place-items-center px-4" data-testid="verify-email-page">
      <Card className="p-8 text-center max-w-md w-full">
        {state === "loading" && (
          <><Loader2 className="h-10 w-10 mx-auto animate-spin text-primary mb-4" />
            <p className="text-sm text-muted-foreground">Confirmation de votre e-mail…</p></>
        )}
        {state === "ok" && (
          <div data-testid="verify-email-success">
            <div className="mx-auto h-16 w-16 rounded-full bg-primary/10 grid place-items-center mb-4">
              <CheckCircle2 className="h-9 w-9 text-primary" />
            </div>
            <h1 className="text-2xl font-bold">E-mail confirmé ✅</h1>
            <p className="text-sm text-muted-foreground mt-2">
              Merci ! Votre adresse est vérifiée. Vous pouvez profiter de ConstruPilot.
            </p>
            <Button className="mt-6" onClick={() => nav("/dashboard")} data-testid="verify-email-cta">
              Accéder à mon tableau de bord
            </Button>
          </div>
        )}
        {state === "error" && (
          <div data-testid="verify-email-error">
            <div className="mx-auto h-16 w-16 rounded-full bg-red-500/10 grid place-items-center mb-4">
              <XCircle className="h-9 w-9 text-red-600" />
            </div>
            <h1 className="text-2xl font-bold">Lien invalide</h1>
            <p className="text-sm text-muted-foreground mt-2">
              Ce lien de confirmation n'est plus valide ou a déjà été utilisé.
            </p>
            <Button variant="outline" className="mt-6" onClick={() => nav("/dashboard")}>
              Retour au tableau de bord
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
