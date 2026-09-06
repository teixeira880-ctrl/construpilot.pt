import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Bell, CheckCircle2, Mail, Eye } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent,
} from "@/components/ui/dropdown-menu";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

const POLL_MS = 30_000;

export function NotificationsBell() {
  const { user } = useAuth();
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const timer = useRef(null);

  const fetchNotifs = async () => {
    try {
      const { data } = await api.get("/quotes/notifications/me");
      setUnread(data.unread || 0);
      setItems(data.notifications || []);
    } catch { /* silent */ }
  };

  useEffect(() => {
    if (!user) return;
    fetchNotifs();
    timer.current = setInterval(fetchNotifs, POLL_MS);
    return () => clearInterval(timer.current);
  }, [user]);

  useEffect(() => { if (open) fetchNotifs(); }, [open]);

  const markRead = async (nid) => {
    try {
      await api.post(`/quotes/notifications/${nid}/read`);
      setItems(prev => prev.map(n => n.notif_id === nid ? { ...n, read: true } : n));
      setUnread(u => Math.max(0, u - 1));
    } catch { /* silent */ }
  };

  const markAll = async () => {
    try {
      await api.post("/quotes/notifications/read-all");
      setItems(prev => prev.map(n => ({ ...n, read: true })));
      setUnread(0);
    } catch { /* silent */ }
  };

  if (!user) return null;

  const iconFor = (type) => {
    if (type === "quote_signed") return <CheckCircle2 className="h-3.5 w-3.5 text-primary" />;
    if (type === "quote_opened") return <Eye className="h-3.5 w-3.5 text-emerald-500" />;
    return <Mail className="h-3.5 w-3.5 text-muted-foreground" />;
  };

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon"
                data-testid="notif-bell-btn"
                className="relative rounded-sm h-9 w-9">
          <Bell className="h-4 w-4" />
          {unread > 0 && (
            <span className="absolute -top-0.5 -right-0.5 h-4 min-w-4 px-1 rounded-full
                             bg-destructive text-destructive-foreground text-[9px]
                             font-extrabold grid place-items-center num"
                  data-testid="notif-badge">
              {unread > 9 ? "9+" : unread}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80 rounded-sm p-0"
                            data-testid="notif-dropdown">
        <div className="flex items-center justify-between border-b border-border p-3">
          <p className="font-display font-bold text-sm">Notifications</p>
          {unread > 0 && (
            <button onClick={markAll} className="text-[10px] text-primary hover:underline"
                    data-testid="notif-mark-all">
              Tout marquer lu
            </button>
          )}
        </div>
        <div className="max-h-96 overflow-y-auto" data-testid="notif-list">
          {items.length === 0 ? (
            <p className="text-xs text-muted-foreground p-6 text-center">
              Aucune notification pour l'instant.
            </p>
          ) : items.map(n => (
            <button key={n.notif_id}
                    onClick={() => { if (!n.read) markRead(n.notif_id); setOpen(false); }}
                    data-testid={`notif-item-${n.notif_id}`}
                    className={`w-full text-left p-3 border-b border-border text-xs flex gap-2 items-start hover:bg-secondary/40 ${n.read ? "opacity-60" : ""}`}>
              <span className="mt-0.5">{iconFor(n.type)}</span>
              <div className="min-w-0 flex-1">
                <p className={`${n.read ? "" : "font-bold"} truncate`}>{n.message}</p>
                <p className="text-[10px] text-muted-foreground num">
                  {new Date(n.created_at).toLocaleString("pt-PT")}
                </p>
              </div>
              {!n.read && <span className="h-1.5 w-1.5 rounded-full bg-primary mt-1.5 shrink-0" />}
            </button>
          ))}
        </div>
        {items.length > 0 && (
          <div className="border-t border-border p-2">
            <Link to="/devis" onClick={() => setOpen(false)}
                  data-testid="notif-see-all"
                  className="block text-center text-[11px] text-primary hover:underline py-1">
              Voir tous les devis envoyés →
            </Link>
          </div>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export default NotificationsBell;
