import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Camera, MapPin, LogIn, LogOut, Loader2, Clock, MessageSquareWarning, Send, Power, ImagePlus } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useI18n } from "@/context/I18nContext";
import { LangToggle } from "@/context/I18nContext";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export default function WorkerApp() {
  const { user, logout } = useAuth();
  const { t } = useI18n();
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState("");
  const [openTs, setOpenTs] = useState(null);
  const [selfie, setSelfie] = useState(null);
  const [gps, setGps] = useState(null);
  const [gpsState, setGpsState] = useState("idle");
  const [busy, setBusy] = useState(false);
  const [mine, setMine] = useState([]);
  const [notes, setNotes] = useState([]);
  const [doubt, setDoubt] = useState("");
  const [photo, setPhoto] = useState(null);
  const [caption, setCaption] = useState("");
  const fileRef = useRef();
  const photoRef = useRef();

  const isWorker = user?.role === "worker";

  const refresh = () => {
    api.get("/hr/me/status").then(({ data }) => setOpenTs(data.open)).catch(() => {});
    api.get("/hr/me/timesheets").then(({ data }) => setMine(data)).catch(() => {});
    api.get("/hr/me/site-notes").then(({ data }) => setNotes(data)).catch(() => {});
  };
  useEffect(() => {
    if (!isWorker) return;
    api.get("/hr/me/projects").then(({ data }) => setProjects(data)).catch(() => {});
    refresh();
  }, [isWorker]);

  const askGps = () => {
    if (!navigator.geolocation) { setGpsState("off"); return; }
    setGpsState("locating");
    navigator.geolocation.getCurrentPosition(
      (pos) => { setGps({ lat: pos.coords.latitude, lng: pos.coords.longitude, accuracy: pos.coords.accuracy }); setGpsState("ok"); },
      () => setGpsState("off"),
      { enableHighAccuracy: true, timeout: 10000 }
    );
  };

  const onFile = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => { setSelfie(reader.result); askGps(); };
    reader.readAsDataURL(file);
  };

  const doClock = async (kind) => {
    if (!selfie) return toast.error(t("hr.w_need_selfie"));
    if (kind === "in" && !projectId) return toast.error(t("hr.w_need_site"));
    setBusy(true);
    try {
      const body = { selfie, lat: gps?.lat, lng: gps?.lng, accuracy: gps?.accuracy };
      if (kind === "in") { body.project_id = projectId; await api.post("/hr/clock-in", body); toast.success(t("hr.w_in_done")); }
      else { await api.post("/hr/clock-out", body); toast.success(t("hr.w_out_done")); }
      setSelfie(null); setGps(null); setGpsState("idle");
      refresh();
    } catch (e) { toast.error(e?.response?.data?.detail || "Erreur"); }
    finally { setBusy(false); }
  };

  const sendDoubt = async () => {
    if (!doubt.trim()) return;
    setBusy(true);
    try {
      await api.post("/hr/site-notes", { project_id: openTs?.project_id || projectId || null, type: "question", message: doubt });
      toast.success(t("hr.w_doubt_sent")); setDoubt(""); refresh();
    } catch { toast.error("Erreur"); }
    finally { setBusy(false); }
  };

  const onPhoto = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setPhoto(reader.result);
    reader.readAsDataURL(file);
  };
  const sendPhoto = async () => {
    if (!photo) return;
    setBusy(true);
    try {
      await api.post("/hr/site-photos", { project_id: openTs?.project_id || projectId || null, photo, caption });
      toast.success(t("hr.w_photo_sent")); setPhoto(null); setCaption("");
    } catch { toast.error("Erreur"); }
    finally { setBusy(false); }
  };

  if (!isWorker) {
    return <div className="min-h-screen grid place-items-center p-6 text-center text-muted-foreground">{t("hr.w_worker_only")}</div>;
  }

  return (
    <div className="min-h-screen bg-background" data-testid="worker-app">
      <header className="flex items-center justify-between px-4 py-3 border-b border-border sticky top-0 bg-background/90 backdrop-blur z-10">
        <span className="font-display font-extrabold">{t("hr.w_hello")}, {user.name?.split(" ")[0]}</span>
        <div className="flex items-center gap-2">
          <LangToggle />
          <Button size="sm" variant="ghost" className="gap-1" onClick={logout} data-testid="worker-logout"><Power className="h-4 w-4" />{t("hr.w_logout")}</Button>
        </div>
      </header>

      <main className="max-w-md mx-auto p-4 grid gap-5">
        {openTs && (
          <div className="surface p-4 rounded-sm border-primary/40 bg-primary/5" data-testid="worker-open-ts">
            <p className="text-sm font-semibold text-primary">{t("hr.w_in_progress")} {new Date(openTs.clock_in).toLocaleTimeString("pt-PT", { hour: "2-digit", minute: "2-digit" })}</p>
            <p className="text-xs text-muted-foreground">{openTs.project_name}</p>
          </div>
        )}

        {!openTs && (
          <div className="grid gap-2">
            <label className="text-sm font-semibold">{t("hr.w_pick_site")}</label>
            <select value={projectId} onChange={(e) => setProjectId(e.target.value)} data-testid="worker-project-select"
              className="w-full rounded-sm border border-border bg-background px-3 py-3 text-base outline-none focus:border-primary">
              <option value="">— {t("hr.w_no_site")} —</option>
              {projects.map((p) => <option key={p.project_id} value={p.project_id}>{p.name}</option>)}
            </select>
          </div>
        )}

        {/* Selfie capture */}
        <div className="surface p-4 rounded-sm grid gap-3">
          {selfie ? (
            <img src={selfie} alt="selfie" className="w-full rounded-sm object-cover max-h-64" data-testid="worker-selfie-preview" />
          ) : (
            <div className="aspect-video rounded-sm bg-secondary grid place-items-center text-muted-foreground">
              <Camera className="h-10 w-10" />
            </div>
          )}
          <input ref={fileRef} type="file" accept="image/*" capture="user" className="hidden" onChange={onFile} data-testid="worker-selfie-input" />
          <Button variant="outline" className="rounded-sm gap-2" onClick={() => fileRef.current?.click()} data-testid="worker-take-selfie">
            <Camera className="h-4 w-4" /> {selfie ? t("hr.w_retake") : t("hr.w_take_selfie")}
          </Button>
          <p className="text-xs text-center flex items-center justify-center gap-1 text-muted-foreground" data-testid="worker-gps-state">
            <MapPin className="h-3.5 w-3.5" />
            {gpsState === "locating" ? t("hr.w_locating") : gpsState === "ok" ? t("hr.w_gps_ok") : gpsState === "off" ? t("hr.w_gps_off") : "—"}
          </p>
        </div>

        {openTs ? (
          <Button size="lg" className="rounded-sm gap-2 h-14 text-base bg-red-600 hover:bg-red-700" disabled={busy} onClick={() => doClock("out")} data-testid="worker-clock-out">
            {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <LogOut className="h-5 w-5" />} {t("hr.w_clock_out")}
          </Button>
        ) : (
          <Button size="lg" className="rounded-sm gap-2 h-14 text-base" disabled={busy} onClick={() => doClock("in")} data-testid="worker-clock-in">
            {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <LogIn className="h-5 w-5" />} {t("hr.w_clock_in")}
          </Button>
        )}

        {/* Site progress photo */}
        <div className="surface p-4 rounded-sm grid gap-2" data-testid="worker-photo-section">
          <p className="text-sm font-semibold flex items-center gap-1.5"><ImagePlus className="h-4 w-4 text-primary" /> {t("hr.w_add_photo")}</p>
          {photo && <img src={photo} alt="preview" className="w-full rounded-sm object-cover max-h-48" data-testid="worker-photo-preview" />}
          <input ref={photoRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={onPhoto} data-testid="worker-photo-input" />
          <div className="flex gap-2">
            <Button variant="outline" className="rounded-sm gap-2 flex-1" onClick={() => photoRef.current?.click()} data-testid="worker-pick-photo">
              <ImagePlus className="h-4 w-4" /> {photo ? t("hr.w_retake") : t("hr.w_add_photo")}
            </Button>
          </div>
          {photo && (
            <>
              <input value={caption} onChange={(e) => setCaption(e.target.value)} placeholder={t("hr.w_photo_caption")}
                className="w-full rounded-sm border border-border bg-background px-3 py-2 text-sm" data-testid="worker-photo-caption" />
              <Button className="rounded-sm gap-2" disabled={busy} onClick={sendPhoto} data-testid="worker-photo-send">
                <Send className="h-4 w-4" /> {t("hr.w_send_photo")}
              </Button>
            </>
          )}
        </div>

        {/* Doubt */}
        <div className="surface p-4 rounded-sm grid gap-2">
          <p className="text-sm font-semibold flex items-center gap-1.5"><MessageSquareWarning className="h-4 w-4 text-amber-500" /> {t("hr.w_new_doubt")}</p>
          <Textarea value={doubt} onChange={(e) => setDoubt(e.target.value)} rows={2} placeholder={t("hr.w_doubt_ph")} className="rounded-sm resize-none" data-testid="worker-doubt-input" />
          <Button variant="outline" className="rounded-sm gap-2" disabled={busy} onClick={sendDoubt} data-testid="worker-doubt-send"><Send className="h-4 w-4" /> {t("hr.w_send")}</Button>
          {notes.slice(0, 4).map((n) => (
            <div key={n.note_id} className="text-xs border-t border-border pt-2">
              <p>{n.message}</p>
              {n.reply && <p className="text-primary mt-1">↳ {n.reply}</p>}
            </div>
          ))}
        </div>

        {/* My hours */}
        <div className="surface p-4 rounded-sm grid gap-2">
          <p className="text-sm font-semibold flex items-center gap-1.5"><Clock className="h-4 w-4" /> {t("hr.w_my_hours")}</p>
          {mine.slice(0, 8).map((r) => (
            <div key={r.entry_id} className="flex justify-between text-xs py-1 border-t border-border first:border-0" data-testid={`worker-ts-${r.entry_id}`}>
              <span>{new Date(r.clock_in).toLocaleDateString("pt-PT")} · {r.project_name}</span>
              <span className="num font-bold">{r.hours != null ? `${r.hours} h` : t("hr.st_open")}</span>
            </div>
          ))}
          {mine.length === 0 && <p className="text-xs text-muted-foreground">—</p>}
        </div>
      </main>
    </div>
  );
}
