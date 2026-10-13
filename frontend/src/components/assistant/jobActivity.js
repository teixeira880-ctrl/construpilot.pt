export const ASSISTANT_JOB_SUBMITTED = "construpilot:assistant-job-submitted";

export function lastConversation(userId) {
  try { return userId ? localStorage.getItem(`assistant-last-${userId}`) : null; }
  catch { return null; }
}

export function rememberConversation(userId, conversationId) {
  try { if (userId && conversationId) localStorage.setItem(`assistant-last-${userId}`, conversationId); }
  catch { /* The conversation also remains available in server history. */ }
}

export function submittedJob(userId, conversationId) {
  // Persist the server acknowledgement even if the Assistant page has unmounted.
  rememberConversation(userId, conversationId);
  window.dispatchEvent(new Event(ASSISTANT_JOB_SUBMITTED));
}
