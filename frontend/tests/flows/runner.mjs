import { indexedDB as fakeIDB, IDBKeyRange as fakeKR } from "fake-indexeddb";
import { JSDOM } from "jsdom";
const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost/" });
for (const k of ["window", "document", "navigator", "localStorage", "HTMLElement", "Node", "MutationObserver", "getComputedStyle", "Event", "KeyboardEvent", "MouseEvent", "HTMLInputElement", "CustomEvent", "FileReader", "NodeFilter", "Element", "HTMLButtonElement", "DocumentFragment", "ShadowRoot", "FocusEvent", "PointerEvent", "DOMRect"]) {
  try { globalThis[k] = dom.window[k]; } catch {}
}
globalThis.ResizeObserver = class { observe(){} unobserve(){} disconnect(){} }; window.ResizeObserver = globalThis.ResizeObserver; globalThis.indexedDB = fakeIDB; globalThis.IDBKeyRange = fakeKR; globalThis.window.scrollTo = () => {}; globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.requestAnimationFrame = cb => setTimeout(cb, 0);
const { run } = await import("./bundle.mjs");
try { await run(); console.log("\nTODOS OS PERCURSOS PASSARAM"); process.exit(0); } catch (e) { console.error(e); process.exit(1); }
