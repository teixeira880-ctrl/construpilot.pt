import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Loader2, Users, Clock, MessageSquareWarning, BarChart3, ArrowRight, Check, X, KeyRound, UserX, MapPin, Download, FileText, ImagePlus } from "lucide-react";
import { api, num } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useBilling } from "@/context/BillingContext";
import { useI18n } from "@/context/I18nContext";
import { SectionTitle } from "@/components/Bits";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";

const ST_KEY = { open: "hr.st_open", pending: "hr.st_pending", validated: "hr.st_validated", rejected: "hr.st_rejected" };
const ST_CLS = {
  open: "bg-blue-500/15 text-blue-600 dark:text-blue-400",
  pending: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
  validated: "bg-primary/15 text-primary",
  rejected: "bg-red-500/15 text-red-600 dark:text-red-400",
};

function Selfie({ path }) {
  const [url, setUrl] = useState(null);
  useEffect(() => {
    let live = true, obj;
    api.get(`/hr/selfie?path=${encodeURIComponent(path)}`, { responseType: "blob" })
      .then((r) => { if (live) { obj = URL.createObjectURL(r.data); setUrl(obj); } })
      .catch(() => {});
    return () => { live = false; if (obj) URL.revokeObjectURL(obj); };
  }, [path]);
  if (!path) return <span className="text-muted-foreground text-xs">—</span>;
  return url
    ? <img src={url} alt="selfie" className="h-10 w-10 rounded-sm object-cover border border-border" />
    : <div className="h-10 w-10 rounded-sm bg-secondary animate-pulse" />;
}

export default function HR() {
  const { user } = useAuth();
  const { tier } = useBilling();
  const { t } = useI18n();

  const allowed = user?.role === "admin" || tier === "pro_business";

  if (!allowed) {
    return (
      <div className="surface rounded-sm p-12 text-center max-w-2xl mx-auto" data-testid="hr-paywall">
        <Users className="h-10 w-10 mx-auto text-primary" />
        <h1 className="font-display text-3xl font-extrabold tracking-tight mt-4">{t("hr.paywall_title")}</h1>
        <p className="mt-4 text-muted-foreground">{t("hr.paywall_desc")}</p>
        <Button className="mt-8 rounded-sm gap-2" data-testid="hr-upgrade-btn"
          onClick={() => (window.location.href = "/tarifs")}>
          {t("hr.see_pb")} <ArrowRight className="h-4 w-4" />
        </Button>
      </div>
    );
  }

  return (
    <div className="grid gap-6" data-testid="hr-page">
      <SectionTitle over={t("hr.over")} title={t("hr.title")}>{t("hr.sub")}</SectionTitle>
      <Tabs defaultValue="workers">
        <TabsList className="rounded-sm flex-wrap h-auto">
          <TabsTrigger value="workers" className="rounded-sm gap-1.5" data-testid="hr-tab-workers"><Users className="h-4 w-4" />{t("hr.tab_workers")}</TabsTrigger>
          <TabsTrigger value="timesheets" className="rounded-sm gap-1.5" data-testid="hr-tab-timesheets"><Clock className="h-4 w-4" />{t("hr.tab_timesheets")}</TabsTrigger>
          <TabsTrigger value="notes" className="rounded-sm gap-1.5" data-testid="hr-tab-notes"><MessageSquareWarning className="h-4 w-4" />{t("hr.tab_notes")}</TabsTrigger>
          <TabsTrigger value="dashboard" className="rounded-sm gap-1.5" data-testid="hr-tab-dashboard"><BarChart3 className="h-4 w-4" />{t("hr.tab_dashboard")}</TabsTrigger>
        </TabsList>
        <TabsContent value="workers" className="mt-6"><WorkersTab t={t} /></TabsContent>
        <TabsContent value="timesheets" className="mt-6"><TimesheetsTab t={t} /></TabsContent>
        <TabsContent value="notes" className="mt-6"><NotesTab t={t} /></TabsContent>
        <TabsContent value="dashboard" className="mt-6"><DashboardTab t={t} /></TabsContent>
      </Tabs>
    </div>
  );
}

function WorkersTab({ t }) {
  const [workers, setWorkers] = useState([]);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", password: "", poste: "", hourly_rate: "" });
  const load = () => api.get("/hr/workers").then(({ data }) => setWorkers(data));
  useEffect(() => { load(); }, []);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const save = async () => {
    if (!form.name || !form.email || !form.password) return toast.error(t("hr.need_identity") || "Champs requis");
    setSaving(true);
    try {
      await api.post("/hr/workers", {
        name: form.name, email: form.email, password: form.password,
        poste: form.poste || null, hourly_rate: form.hourly_rate ? Number(form.hourly_rate) : null,
      });
      toast.success(t("hr.worker_created"));
      setOpen(false); setForm({ name: "", email: "", password: "", poste: "", hourly_rate: "" });
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || t("hr.save_fail") || "Erreur"); }
    finally { setSaving(false); }
  };
  const resetPwd = async (w) => {
    const pwd = window.prompt(t("hr.new_pwd"));
    if (!pwd) return;
    try { await api.post(`/hr/workers/${w.worker_id}/reset-password`, { password: pwd }); toast.success(t("hr.pwd_reset")); }
    catch (e) { toast.error(e?.response?.data?.detail || "Erreur"); }
  };
  const deactivate = async (w) => {
    if (!window.confirm(`${t("hr.deactivate")} ${w.name} ?`)) return;
    try { await api.delete(`/hr/workers/${w.worker_id}`); toast.success(t("hr.worker_deactivated")); load(); }
    catch { toast.error("Erreur"); }
  };

  return (
    <div className="grid gap-4">
      <div className="flex justify-end">
        <Button onClick={() => setOpen(true)} className="rounded-sm gap-2" data-testid="hr-new-worker-btn">
          <Plus className="h-4 w-4" /> {t("hr.new_worker")}
        </Button>
      </div>
      {workers.length === 0 ? (
        <div className="surface p-10 text-center text-muted-foreground" data-testid="hr-workers-empty">{t("hr.no_workers")}</div>
      ) : (
        <div className="grid gap-2">
          {workers.map((w) => (
            <div key={w.worker_id} className={`surface p-4 rounded-sm flex flex-wrap items-center gap-3 ${!w.active ? "opacity-50" : ""}`} data-testid={`hr-worker-${w.worker_id}`}>
              <div className="min-w-0 flex-1">
                <p className="font-display font-semibold">{w.name} {!w.active && <span className="text-xs">(inactif)</span>}</p>
                <p className="text-xs text-muted-foreground">{w.email} · {w.poste || "—"}{w.hourly_rate ? ` · ${w.hourly_rate} €/h` : ""}</p>
              </div>
              <Button size="sm" variant="outline" className="rounded-sm gap-1 h-8" onClick={() => resetPwd(w)} data-testid={`hr-reset-${w.worker_id}`}>
                <KeyRound className="h-3.5 w-3.5" /> {t("hr.reset_pwd")}
              </Button>
              {w.active && (
                <Button size="sm" variant="ghost" className="rounded-sm gap-1 h-8 text-red-500" onClick={() => deactivate(w)} data-testid={`hr-deactivate-${w.worker_id}`}>
                  <UserX className="h-3.5 w-3.5" /> {t("hr.deactivate")}
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>{t("hr.new_worker")}</DialogTitle>
            <DialogDescription>{t("hr.sub")}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-3">
            <div><Label>{t("hr.name")}</Label><Input value={form.name} onChange={set("name")} className="rounded-sm mt-1" data-testid="hr-worker-name" /></div>
            <div><Label>{t("hr.email")}</Label><Input type="email" value={form.email} onChange={set("email")} className="rounded-sm mt-1" data-testid="hr-worker-email" /></div>
            <div><Label>{t("hr.password")}</Label><Input value={form.password} onChange={set("password")} className="rounded-sm mt-1" data-testid="hr-worker-password" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>{t("hr.poste")}</Label><Input value={form.poste} onChange={set("poste")} className="rounded-sm mt-1" data-testid="hr-worker-poste" /></div>
              <div><Label>{t("hr.hourly_rate")}</Label><Input type="number" value={form.hourly_rate} onChange={set("hourly_rate")} className="rounded-sm mt-1 num" data-testid="hr-worker-rate" /></div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)} className="rounded-sm">{t("hr.cancel")}</Button>
            <Button onClick={save} disabled={saving} className="rounded-sm gap-2" data-testid="hr-worker-save">
              {saving && <Loader2 className="h-4 w-4 animate-spin" />} {t("hr.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function TimesheetsTab({ t }) {
  const [rows, setRows] = useState([]);
  const load = () => api.get("/hr/timesheets").then(({ data }) => setRows(data));
  useEffect(() => { load(); }, []);
  const act = async (id, status) => {
    try {
      await api.post(`/hr/timesheets/${id}/validate`, { status });
      toast.success(status === "validated" ? t("hr.validated_toast") : t("hr.rejected_toast"));
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Erreur"); }
  };
  if (rows.length === 0) return <div className="surface p-10 text-center text-muted-foreground" data-testid="hr-timesheets-empty">{t("hr.no_timesheets")}</div>;
  return (
    <div className="grid gap-2" data-testid="hr-timesheets">
      {rows.map((r) => (
        <div key={r.entry_id} className="surface p-3 rounded-sm flex flex-wrap items-center gap-3" data-testid={`hr-ts-${r.entry_id}`}>
          <div className="flex gap-1">
            <Selfie path={r.selfie_in} /><Selfie path={r.selfie_out} />
          </div>
          <div className="min-w-0 flex-1">
            <p className="font-semibold text-sm">{r.worker_name} · {r.project_name}</p>
            <p className="text-xs text-muted-foreground">
              {new Date(r.clock_in).toLocaleString("fr-FR")}{r.clock_out ? ` → ${new Date(r.clock_out).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}` : ""}
              {r.gps_in?.lat ? <> · <a className="inline-flex items-center gap-0.5 hover:text-primary" target="_blank" rel="noreferrer" href={`https://maps.google.com/?q=${r.gps_in.lat},${r.gps_in.lng}`}><MapPin className="h-3 w-3" />{t("hr.gps")}</a></> : null}
            </p>
          </div>
          <span className="num font-bold">{r.hours != null ? `${r.hours} h` : "—"}</span>
          {r.out_of_zone && (
            <span className="px-2 py-1 rounded-sm text-[10px] font-semibold uppercase bg-red-500/15 text-red-600 dark:text-red-400" data-testid={`hr-outofzone-${r.entry_id}`} title={r.distance_in_m ? `${Math.round(r.distance_in_m)} m` : ""}>
              ⚠ {t("hr.out_of_zone")}
            </span>
          )}
          <span className={`px-2.5 py-1 rounded-sm text-[11px] font-semibold uppercase ${ST_CLS[r.status] || ""}`}>{t(ST_KEY[r.status] || "")}</span>
          {r.status === "pending" && (
            <div className="flex gap-1">
              <Button size="icon" variant="ghost" className="h-8 w-8 text-primary" onClick={() => act(r.entry_id, "validated")} data-testid={`hr-validate-${r.entry_id}`}><Check className="h-4 w-4" /></Button>
              <Button size="icon" variant="ghost" className="h-8 w-8 text-red-500" onClick={() => act(r.entry_id, "rejected")} data-testid={`hr-reject-${r.entry_id}`}><X className="h-4 w-4" /></Button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function NotesTab({ t }) {
  const [rows, setRows] = useState([]);
  const [photos, setPhotos] = useState([]);
  const [replies, setReplies] = useState({});
  const load = () => {
    api.get("/hr/site-notes").then(({ data }) => setRows(data));
    api.get("/hr/site-photos").then(({ data }) => setPhotos(data)).catch(() => {});
  };
  useEffect(() => { load(); }, []);
  const send = async (id) => {
    const reply = replies[id];
    if (!reply?.trim()) return;
    try { await api.post(`/hr/site-notes/${id}/reply`, { reply }); toast.success(t("hr.replied")); load(); }
    catch { toast.error("Erreur"); }
  };
  return (
    <div className="grid gap-6 max-w-3xl">
      <div className="grid gap-3" data-testid="hr-notes">
        {rows.length === 0 && <div className="surface p-8 text-center text-muted-foreground" data-testid="hr-notes-empty">{t("hr.no_notes")}</div>}
        {rows.map((n) => (
          <div key={n.note_id} className="surface p-4 rounded-sm" data-testid={`hr-note-${n.note_id}`}>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className={`px-2 py-0.5 rounded-sm ${n.type === "question" ? "bg-amber-500/15 text-amber-600" : "bg-secondary"}`}>
                {n.type === "question" ? t("hr.type_question") : t("hr.type_comment")}
              </span>
              <span>{n.worker_name}{n.project_name ? ` · ${n.project_name}` : ""}</span>
              <span className="ml-auto">{n.status === "answered" ? t("hr.answered") : t("hr.open_status")}</span>
            </div>
            <p className="mt-2 text-sm">{n.message}</p>
            {n.reply ? (
              <p className="mt-3 text-sm border-l-2 border-primary pl-3 text-muted-foreground">↳ {n.reply}</p>
            ) : (
              <div className="mt-3 flex gap-2">
                <Input value={replies[n.note_id] || ""} onChange={(e) => setReplies((r) => ({ ...r, [n.note_id]: e.target.value }))}
                  placeholder={t("hr.reply_ph")} className="rounded-sm" data-testid={`hr-reply-input-${n.note_id}`} />
                <Button className="rounded-sm" onClick={() => send(n.note_id)} data-testid={`hr-reply-btn-${n.note_id}`}>{t("hr.reply")}</Button>
              </div>
            )}
          </div>
        ))}
      </div>

      <div data-testid="hr-photos">
        <p className="font-display font-bold text-sm mb-3">{t("hr.photos_title")}</p>
        {photos.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="hr-photos-empty">{t("hr.no_photos")}</p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
            {photos.map((p) => (
              <div key={p.photo_id} className="surface rounded-sm overflow-hidden" data-testid={`hr-photo-${p.photo_id}`}>
                <Selfie path={p.path} />
                <div className="p-2">
                  <p className="text-xs truncate">{p.caption || "—"}</p>
                  <p className="text-[10px] text-muted-foreground">{p.worker_name} · {p.project_name || ""}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function DashboardTab({ t }) {
  const [data, setData] = useState(null);
  useEffect(() => { api.get("/hr/dashboard").then(({ data }) => setData(data)); }, []);
  const dl = async (fmt) => {
    try {
      const res = await api.get(`/hr/export/${fmt}`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = `paie.${fmt}`; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Export impossible"); }
  };
  if (!data) return null;
  return (
    <div className="grid gap-6" data-testid="hr-dashboard">
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="outline" size="sm" className="rounded-sm gap-2" onClick={() => dl("csv")} data-testid="hr-export-csv">
          <Download className="h-4 w-4" /> {t("hr.export_csv")}
        </Button>
        <Button variant="outline" size="sm" className="rounded-sm gap-2" onClick={() => dl("pdf")} data-testid="hr-export-pdf">
          <FileText className="h-4 w-4" /> {t("hr.export_pdf")}
        </Button>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div className="surface p-4 rounded-sm"><p className="num text-2xl font-extrabold">{data.total_hours} h</p><p className="text-xs text-muted-foreground mt-1">{t("hr.total_hours")}</p></div>
        <div className="surface p-4 rounded-sm"><p className="num text-2xl font-extrabold">{num(data.entries)}</p><p className="text-xs text-muted-foreground mt-1">{t("hr.entries")}</p></div>
        <div className="surface p-4 rounded-sm border-amber-500/30"><p className="num text-2xl font-extrabold text-amber-600 dark:text-amber-400">{num(data.pending)}</p><p className="text-xs text-muted-foreground mt-1">{t("hr.pending")}</p></div>
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        <div className="surface p-4 rounded-sm">
          <p className="text-[11px] font-bold uppercase tracking-widest text-primary mb-3">{t("hr.by_worker")}</p>
          {data.by_worker.map((w) => (
            <div key={w.worker_id} className="flex justify-between text-sm py-1">
              <span>{w.worker_name}</span><span className="num font-bold">{w.hours} h <span className="text-primary text-xs">({w.validated_hours} {t("hr.st_validated").toLowerCase()})</span></span>
            </div>
          ))}
          {data.by_worker.length === 0 && <p className="text-sm text-muted-foreground">—</p>}
        </div>
        <div className="surface p-4 rounded-sm">
          <p className="text-[11px] font-bold uppercase tracking-widest text-primary mb-3">{t("hr.by_project")}</p>
          {data.by_project.map((p) => (
            <div key={p.project_id} className="flex justify-between text-sm py-1"><span>{p.project_name}</span><span className="num font-bold">{p.hours} h</span></div>
          ))}
          {data.by_project.length === 0 && <p className="text-sm text-muted-foreground">—</p>}
        </div>
      </div>
      <GeofenceManager t={t} />
    </div>
  );
}

function GeofenceManager({ t }) {
  const [projects, setProjects] = useState([]);
  const load = () => api.get("/hr/projects").then(({ data }) => setProjects(data));
  useEffect(() => { load(); }, []);
  const setZone = (p) => {
    if (!navigator.geolocation) return toast.error(t("hr.w_gps_off"));
    navigator.geolocation.getCurrentPosition(async (pos) => {
      try {
        await api.put(`/hr/projects/${p.project_id}/geofence`, {
          lat: pos.coords.latitude, lng: pos.coords.longitude, radius: 300,
        });
        toast.success(t("hr.geofence_saved")); load();
      } catch { toast.error("Erreur"); }
    }, () => toast.error(t("hr.w_gps_off")), { enableHighAccuracy: true, timeout: 10000 });
  };
  return (
    <div className="surface p-4 rounded-sm" data-testid="hr-geofence">
      <p className="text-[11px] font-bold uppercase tracking-widest text-primary mb-3 flex items-center gap-1.5">
        <MapPin className="h-3.5 w-3.5" /> {t("hr.geofence")}
      </p>
      <div className="grid gap-2">
        {projects.map((p) => (
          <div key={p.project_id} className="flex items-center justify-between gap-2 text-sm py-1" data-testid={`hr-geofence-${p.project_id}`}>
            <span className="min-w-0 truncate">{p.name}</span>
            <span className="text-xs text-muted-foreground shrink-0">
              {p.site_lat != null ? `${p.site_lat.toFixed(4)}, ${p.site_lng.toFixed(4)} · ${p.geofence_radius || 300} m` : t("hr.no_geo")}
            </span>
            <Button size="sm" variant="outline" className="rounded-sm gap-1 h-7 text-[11px] shrink-0" onClick={() => setZone(p)} data-testid={`hr-setzone-${p.project_id}`}>
              <MapPin className="h-3 w-3" /> {t("hr.use_my_pos")}
            </Button>
          </div>
        ))}
        {projects.length === 0 && <p className="text-sm text-muted-foreground">—</p>}
      </div>
    </div>
  );
}
