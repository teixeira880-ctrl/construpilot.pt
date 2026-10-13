import { Loader2, ShieldAlert, RotateCcw } from "lucide-react";
import { usePermissions } from "@/context/PermissionContext";
import { useWorkspaceCopy } from "./copy";
import { Button } from "@/components/ui/button";

export const PermissionNotice = ({ denied = false }) => {
  const { loading, error, refresh } = usePermissions();
  const ui = useWorkspaceCopy();
  if (!loading && !error && !denied) return null;
  return <div className="dashboard-error" role={loading ? "status" : "alert"} data-testid="workspace-permission-notice">
    {loading ? <Loader2 size={18} className="animate-spin" /> : <ShieldAlert size={18} />}
    <span>{ui(loading ? "permissionsLoading" : error ? "permissionsError" : "accessDenied")}</span>
    {error && <Button variant="outline" onClick={refresh} data-testid="workspace-permissions-retry"><RotateCcw size={16} />{ui("retry")}</Button>}
  </div>;
};