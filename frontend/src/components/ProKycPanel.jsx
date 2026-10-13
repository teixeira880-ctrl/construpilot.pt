import { useEffect, useState } from "react";
import { FileText, ShieldCheck, ShieldX, Eye, Loader2, BadgeCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { toast } from "sonner";

const STATUS_STYLE = {
  pending: "bg-amber-500/15 text-amber-600",
  verified: "bg-emerald-500/15 text-emerald-600",
  rejected: "bg-red-500/15 text-red-600",
};
const STATUS_LABEL = { pending: "Em espera", verified: "Validado", rejected: "Recusado" };

export default function ProKycPanel() {
  const [rows, setRows] = useState([]);
  const [filter, setFilter] = useState("pending");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");

  const load = () => {
    setLoading(true);
    api.get(`/auth/admin/kyc-pros${filter ? `?status=${filter}` : ""}`)
      .then(({ data }) => setRows(data || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [filter]);

  const viewDoc = async (userId, kind) => {
    setBusy(`${userId}-${kind}`);
    try {
      const res = await api.get(`/auth/admin/kyc-pros/${userId}/doc/${kind}`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      window.open(url, "_blank", "noopener");
    } catch {
      toast.error("Documento indisponível");
    } finally { setBusy(""); }
  };

  const review = async (userId, approve) => {
    let reason = null;
    if (!approve) {
      reason = window.prompt("Motivo da recusa (visível pelo utilizador):", "Documentos ilegíveis ou não conformes");
      if (reason === null) return;
    }
    setBusy(`${userId}-review`);
    try {
      await api.post("/auth/admin/kyc-pros/review", { user_id: userId, approve, reason });
      toast.success(approve ? "Conta profissional validada" : "Conta profissional recusada");
      setRows((prev) => prev.filter((r) => r.user_id !== userId || filter === ""));
      if (filter === "") load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Ação impossível");
    } finally { setBusy(""); }
  };

  return (
    <div className="space-y-4" data-testid="pro-kyc-panel">
      <div className="flex items-center gap-2">
        <BadgeCheck className="h-5 w-5 text-primary" />
        <h2 className="font-bold text-lg">Validação das contas Pro</h2>
      </div>
      <div className="flex gap-2">
        {[["pending", "Em espera"], ["verified", "Validados"], ["rejected", "Recusados"], ["", "Todos"]].map(([v, l]) => (
          <button key={v} onClick={() => setFilter(v)}
                  data-testid={`kyc-filter-${v || "all"}`}
                  className={`text-xs px-3 py-1.5 rounded-sm border ${filter === v ? "bg-primary text-white border-primary" : "border-border"}`}>
            {l}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground py-6 text-center">A carregar…</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted-foreground py-6 text-center" data-testid="kyc-empty">Nenhuma conta nesta categoria.</p>
      ) : (
        <div className="space-y-2">
          {rows.map((r) => (
            <div key={r.user_id} className="surface p-4" data-testid={`kyc-pro-${r.user_id}`}>
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="font-semibold">{r.name || r.email}</p>
                    <span className="text-[10px] font-bold uppercase bg-secondary px-1.5 py-0.5 rounded">
                      {r.account_type === "pro_business" ? "Pro Business" : "Pro"}
                    </span>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${STATUS_STYLE[r.kyc_status] || ""}`}>
                      {STATUS_LABEL[r.kyc_status] || r.kyc_status}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground num mt-0.5">
                    {r.email} · NIF {r.siret || "—"}
                  </p>
                  {r.kyc_rejection_reason && (
                    <p className="text-xs text-red-600 mt-1">Motivo recusa: {r.kyc_rejection_reason}</p>
                  )}
                </div>
              </div>
              <div className="flex flex-wrap gap-2 mt-3">
                <Button size="sm" variant="outline" className="rounded-sm gap-1 h-8"
                        disabled={!r.has_kbis || busy === `${r.user_id}-kbis`}
                        onClick={() => viewDoc(r.user_id, "kbis")}
                        data-testid={`kyc-view-kbis-${r.user_id}`}>
                  {busy === `${r.user_id}-kbis` ? <Loader2 className="h-3 w-3 animate-spin" /> : <FileText className="h-3 w-3" />}
                  Certidão permanente {r.has_kbis ? "" : "(em falta)"}
                </Button>
                <Button size="sm" variant="outline" className="rounded-sm gap-1 h-8"
                        disabled={!r.has_decennale || busy === `${r.user_id}-decennale`}
                        onClick={() => viewDoc(r.user_id, "decennale")}
                        data-testid={`kyc-view-decennale-${r.user_id}`}>
                  {busy === `${r.user_id}-decennale` ? <Loader2 className="h-3 w-3 animate-spin" /> : <Eye className="h-3 w-3" />}
                  Alvará / seguro RC {r.has_decennale ? "" : "(em falta)"}
                </Button>
                {r.kyc_status !== "verified" && (
                  <Button size="sm" className="rounded-sm gap-1 h-8 bg-emerald-600 hover:bg-emerald-700 text-white"
                          disabled={busy === `${r.user_id}-review`}
                          onClick={() => review(r.user_id, true)}
                          data-testid={`kyc-approve-${r.user_id}`}>
                    <ShieldCheck className="h-3 w-3" /> Validar
                  </Button>
                )}
                {r.kyc_status !== "rejected" && (
                  <Button size="sm" variant="outline" className="rounded-sm gap-1 h-8 border-red-300 text-red-600"
                          disabled={busy === `${r.user_id}-review`}
                          onClick={() => review(r.user_id, false)}
                          data-testid={`kyc-reject-${r.user_id}`}>
                    <ShieldX className="h-3 w-3" /> Recusar
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
