// Tests locaux du protocole : node --test frontend/tests/assistant-stream.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const source = fs.readFileSync(new URL('../src/lib/assistantStream.js', import.meta.url), 'utf8');
const { streamAssistant } = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));

async function withResponse(t, chunks, run) {
  const savedFetch = globalThis.fetch, savedStorage = globalThis.localStorage;
  let cancelled = false, released = false;
  const reader = { read: async () => chunks.length ? { value: chunks.shift(), done: false } : { done: true },
    cancel: async () => { cancelled = true; }, releaseLock: () => { released = true; } };
  globalThis.localStorage = { getItem: () => 'test-only' };
  globalThis.fetch = async () => ({ ok: true, body: { getReader: () => reader } });
  t.after(() => { globalThis.fetch = savedFetch; globalThis.localStorage = savedStorage; });
  try { await run(); } finally { assert.ok(cancelled); assert.ok(released); }
}

test('UTF-8 fragmenté et délimiteurs CRLF', async t => {
  const bytes = new TextEncoder().encode('data: {"type":"delta","text":"béton"}\r\n\r\ndata: {"type":"done","message":{"content":"béton"}}\r\n\r\n');
  const events = [];
  await withResponse(t, [...bytes].map(b => new Uint8Array([b])), async () => {
    await streamAssistant({}, { onEvent: e => events.push(e) });
    assert.equal(events[0].text, 'béton'); assert.equal(events[1].type, 'done');
  });
});

test('Coupure sans done rejetée', async t => {
  await withResponse(t, [new TextEncoder().encode('data: {"type":"delta","text":"partiel"}\n\n')], async () => {
    await assert.rejects(streamAssistant({}, { onEvent() {} }), /interrompue/);
  });
});

test('Erreur serveur propagée sans faux succès', async t => {
  await withResponse(t, [new TextEncoder().encode('data: {"type":"error","error":"test indisponible"}\n\n')], async () => {
    await assert.rejects(streamAssistant({}, { onEvent() {} }), /test indisponible/);
  });
});

test('Dernier événement sans ligne vide accepté', async t => {
  await withResponse(t, [new TextEncoder().encode('data: {"type":"done","message":{}}')], async () => {
    const events = []; await streamAssistant({}, { onEvent: e => events.push(e) }); assert.equal(events.length, 1);
  });
});
