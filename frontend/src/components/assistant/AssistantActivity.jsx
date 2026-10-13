import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Loader2, WifiOff } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useStudioCopy } from "./studioCopy";
import { ASSISTANT_JOB_SUBMITTED } from "./jobActivity";
import "./AssistantActivity.css";

export function AssistantActivity() {
  const { user } = useAuth();
  const userId = user?.user_id;
  const copy = useStudioCopy();
  const [activity, setActivity] = useState({ userId: null, jobs: [], offline: false });
  useEffect(() => {
    if (!userId) return;
    let active = true, pending = false, timer;
    const poll = async () => {
      if (!active || pending) return;
      clearTimeout(timer); pending = true;
      let authorised = true;
      try {
        const { data } = await api.get("/assistant/jobs");
        if (active) setActivity({ userId, jobs: data.jobs || [], offline: false });
      } catch (error) {
        authorised = ![401, 403].includes(error.response?.status);
        if (active) setActivity(old => authorised ? { ...old, offline: true } : { userId, jobs: [], offline: false });
      } finally {
        pending = false;
        if (active && authorised) timer = setTimeout(poll, document.hidden ? 30000 : 5000);
      }
    };
    const visible = () => { if (!document.hidden) poll(); };
    poll();
    window.addEventListener(ASSISTANT_JOB_SUBMITTED, poll);
    document.addEventListener("visibilitychange", visible);
    return () => {
      active = false; clearTimeout(timer);
      window.removeEventListener(ASSISTANT_JOB_SUBMITTED, poll);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [userId]);
  if (activity.userId !== userId || !activity.jobs.length) return null;
  const label = `${copy(activity.offline ? "activityOffline" : "activity")} (${activity.jobs.length})`;
  return <Link to={`/assistant?conversation=${encodeURIComponent(activity.jobs[0].conversation_id)}`}
    className="workspace-icon-button assistant-activity relative text-primary" title={label} aria-label={label}
    data-testid="assistant-global-activity">
    {activity.offline ? <WifiOff size={19} /> : <Loader2 size={19} className="animate-spin motion-reduce:animate-none" />}
    <span className="absolute -right-1 -top-1 rounded-full bg-primary text-primary-foreground text-[9px] min-w-4 h-4 px-1 flex items-center justify-center" aria-hidden="true">{activity.jobs.length}</span>
    <span className="sr-only" role="status">{label}</span>
  </Link>;
}
