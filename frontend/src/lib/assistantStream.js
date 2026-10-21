export async function streamAssistant(payload, { signal, onEvent }) {
  const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/assistant/message/stream`, {
    method: "POST", signal, credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let detail = "Assistente indisponível";
    try { detail = (await res.json()).detail || detail; } catch { /* ignore */ }
    throw new Error(detail);
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "", completed = false;
  const dispatch = (block) => {
    const data = block.split(/\r?\n/).filter(l => l.startsWith("data:")).map(l => l.slice(5).trimStart()).join("\n");
    if (!data) return;
    const event = JSON.parse(data);
    if (event.type === "error") throw new Error(event.error || "Assistente indisponível");
    if (event.type === "done") completed = true;
    onEvent(event);
  };
  try {
    for (;;) {
      const { value, done } = await reader.read();
      buf += done ? dec.decode() : dec.decode(value, { stream: true });
      const parts = buf.split(/\r?\n\r?\n/);
      buf = parts.pop();
      for (const part of parts) dispatch(part);
      if (done) break;
    }
    if (buf.trim()) dispatch(buf);
    if (!completed) throw new Error("Ligação interrompida antes do fim da resposta. Volte a enviar o seu pedido.");
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
