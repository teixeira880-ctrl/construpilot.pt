import { Fragment, useEffect, useRef, useState } from "react";
import { Loader2, StopCircle, X } from "lucide-react";
import { api } from "@/lib/api";
import { MessageBubble } from "./MessageBubble";
import { useBackgroundCopy } from "./backgroundCopy";

export const useConversationJobs = (conversationId, onData) => {
  const callback = useRef(onData);
  callback.current = onData;
  const [error, setError] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    if (!conversationId) return;
    let active = true, timer;
    const poll = async () => {
      let running = true;
      try {
        const { data } = await api.get(`/assistant/conversations/${conversationId}`);
        if (!active) return;
        setError(false); callback.current(data);
        running = data.jobs?.some((job) => ["preparing", "queued", "running"].includes(job.status));
      } catch { if (active) setError(true); }
      if (active) timer = setTimeout(poll, running ? 1200 : 5000);
    };
    poll();
    return () => { active = false; clearTimeout(timer); };
  }, [conversationId, refresh]);
  return { error, refresh: () => setRefresh((n) => n + 1) };
};

export const ConversationJobs = ({ conversation, onCorrect, onCancel, onResume }) => {
  const copy = useBackgroundCopy();
  const jobs = conversation?.jobs || [];
  const messages = conversation?.messages || [];
  const completed = new Set(messages.filter((m) => m.role === "assistant").map((m) => m.request_id));
  return messages.map((message, index) => {
    const job = message.role === "user" && jobs.find((item) => item.request_id === message.request_id);
    // A saved partial answer must not hide an interruption or its resume action.
    const pending = job && (job.status !== "completed" || !completed.has(job.request_id));
    const live = pending && !completed.has(job.request_id) && job.live && ["running", "completed", "interrupted", "failed", "cancelled"].includes(job.status);
    return <Fragment key={message.message_id || index}>
      <MessageBubble m={message} testId={`assistant-msg-${message.role}-${index}`} onCorrect={onCorrect} />
      {live && <MessageBubble m={job.live} live={job.status === "running"} testId={`assistant-job-reply-${job.job_id}`} />}
      {pending && job.status !== "completed" && <div className="border-l-2 border-primary/40 ps-3 py-2 space-y-2 text-xs" data-testid={`assistant-job-${job.job_id}`} data-job-status={job.status}>
        <p role={job.status === "failed" ? "alert" : "status"} className="flex gap-2 items-center" data-testid={`assistant-job-status-${job.job_id}`}>
          {["preparing", "queued", "running"].includes(job.status) && <Loader2 size={14} className="animate-spin shrink-0" />}{job.cancel_requested && job.status === "running" ? copy("stopping") : job.error || copy(job.status)}
        </p>
        {["queued", "running", "preparing"].includes(job.status) ? <button disabled={job.cancel_requested} className="inline-flex gap-1 items-center underline min-h-8" data-testid={`assistant-job-cancel-${job.job_id}`} onClick={() => onCancel(job.job_id)}>{job.status === "running" ? <StopCircle size={14} /> : <X size={14} />}{copy(job.status === "running" ? "stop" : "cancel")}</button>
          : <button className="underline min-h-8" data-testid={`assistant-job-resume-${job.job_id}`} onClick={() => onResume(message.content)}>{copy("retry")}</button>}
      </div>}
    </Fragment>;
  });
};
