/* Cliente SSE para o Assistente BTP.
 *
 * Usamos `fetch` + `ReadableStream` em vez de `EventSource` porque
 * `EventSource` não suporta headers customizados (`Authorization`).
 * O backend responde com `text/event-stream` com blocos no formato:
 *     event: <tipo>
 *     data: <json>
 *
 * Esta função devolve um `AsyncGenerator` que entrega objectos
 * `{type, data}` em tempo real.
 */

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

export async function* streamChat({ prompt, attachments = [], conversationId = null, signal } = {}) {
  const token = localStorage.getItem("construpilot_token");
  const resp = await fetch(`${BACKEND_URL}/api/btp-assistant/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      Accept: "text/event-stream",
    },
    body: JSON.stringify({
      prompt,
      attachments,
      conversation_id: conversationId,
      stream: true,
    }),
    signal,
  });

  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(`chat HTTP ${resp.status}: ${text.slice(0, 200)}`);
  }
  if (!resp.body) throw new Error("sem stream no corpo da resposta");

  const reader = resp.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Blocos SSE separados por \n\n
      let idx;
      while ((idx = buffer.indexOf("\n\n")) >= 0) {
        const bloco = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const ev = _parsePacote(bloco);
        if (ev) yield ev;
      }
    }
  } finally {
    try { reader.releaseLock(); } catch { /* noop */ }
  }
}

function _parsePacote(bloco) {
  const linhas = bloco.split("\n");
  let tipo = "message";
  let dataRaw = "";
  for (const linha of linhas) {
    if (linha.startsWith("event:")) tipo = linha.slice(6).trim();
    else if (linha.startsWith("data:")) dataRaw += linha.slice(5).trim();
  }
  if (!dataRaw) return null;
  try {
    const parsed = JSON.parse(dataRaw);
    // O servidor emite {type, data, timestamp_iso} dentro de data:
    if (parsed && parsed.type && parsed.data) {
      return { type: parsed.type, data: parsed.data, ts: parsed.timestamp_iso };
    }
    return { type: tipo, data: parsed };
  } catch {
    return { type: tipo, data: { raw: dataRaw } };
  }
}


export async function confirmTool({ conversationId, toolCallId, name, args, confirmed }) {
  const token = localStorage.getItem("construpilot_token");
  const r = await fetch(`${BACKEND_URL}/api/btp-assistant/confirm`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      conversation_id: conversationId,
      tool_call_id: toolCallId,
      name,
      arguments: args || {},
      confirmed: Boolean(confirmed),
    }),
  });
  if (!r.ok) throw new Error(`confirm HTTP ${r.status}`);
  return r.json();
}


export async function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      // dataURL = "data:mime;base64,xxx" — devolvemos só o base64
      const commaIdx = result.indexOf(",");
      resolve(commaIdx >= 0 ? result.slice(commaIdx + 1) : result);
    };
    reader.onerror = () => reject(reader.error || new Error("falha a ler ficheiro"));
    reader.readAsDataURL(file);
  });
}
