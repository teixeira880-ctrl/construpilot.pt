import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export function StudyRunning() {
  const { user } = useAuth(); const nav = useNavigate();
  const [jobs,setJobs] = useState([]); const seen = useRef(new Set());
  useEffect(() => {
    let stopped=false, busy=false; seen.current=new Set(); setJobs([]);
    if (!user) return undefined;
    const poll=async()=>{
      if(busy) return; busy=true;
      try {
        const {data}=await api.get("/pc/study-jobs"); if(stopped) return;
        const all=data.jobs||[], active=all.filter(j=>["queued","running","committing"].includes(j.status));
        for(const j of all.filter(j=>seen.current.has(j.job_id)&&!["queued","running","committing"].includes(j.status))) {
          const options={action:{label:"Ouvrir",onClick:()=>nav(`/plan?open=${encodeURIComponent(j.plan_id)}&study=1`)}};
          if(j.status==="completed") toast.success("Étude et devis disponibles",options);
          else if(j.status!=="cancelled") toast.error(j.error||"Étude interrompue",options);
        }
        seen.current=new Set(active.map(j=>j.job_id)); setJobs(active);
      } catch { /* Keep the last known state during a transient network failure. */ }
      finally {busy=false;}
    };
    poll();const timer=setInterval(poll,4000);return()=>{stopped=true;clearInterval(timer);};
  },[user,nav]);
  if(!jobs.length)return null;
  return <button data-testid="study-running-indicator" onClick={()=>nav(`/plan?open=${encodeURIComponent(jobs[0].plan_id)}&study=1`)} className="fixed left-4 bottom-[calc(8.75rem+env(safe-area-inset-bottom))] md:bottom-16 z-50 max-w-[calc(100vw-2rem)] flex items-center gap-2 rounded-full border border-[#925535]/40 bg-card/95 backdrop-blur px-3 py-2 shadow-lg text-xs"><Loader2 size={15} className="animate-spin shrink-0 text-[#925535]"/><span>{jobs.length} étude{jobs.length>1?"s":""} en cours · {jobs[0].progress?.completed_pages||0}/{jobs[0].progress?.total_pages||"…"} pages</span></button>;
}
