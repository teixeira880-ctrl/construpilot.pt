import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { WorkDraftCard } from "../WorkDraftCard";
import { api } from "@/lib/api";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), put: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

global.IS_REACT_ACT_ENVIRONMENT = true;
const initial = { draft_id: "work_test", kind: "email", title: "Objet", recipient: "", body: "Texte initial", revision: 0 };
let container, root;
beforeEach(() => {
  jest.resetAllMocks();
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
  api.get.mockResolvedValue({ data: { ...initial } });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
const mount = async () => act(async () => { root.render(<WorkDraftCard initial={initial} />); });
const button = text => [...container.querySelectorAll("button")].find(b => b.textContent === text);
const click = async text => act(async () => { button(text).click(); });
const type = async value => act(async () => {
  const textarea = container.querySelector("textarea");
  Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set.call(textarea, value);
  textarea.dispatchEvent(new Event("input", { bubbles: true }));
});

test("bloque la saisie pendant le chargement de la version actuelle", async () => {
  let resolve;
  api.get.mockImplementation(() => new Promise(r => { resolve = r; }));
  await mount(); expect(container.querySelector("fieldset").disabled).toBe(true);
  await act(async () => resolve({ data: initial }));
  expect(container.querySelector("fieldset").disabled).toBe(false);
});

test("conserve le texte saisi lorsqu'une révision IA arrive", async () => {
  await mount(); await type("Ma correction non enregistrée");
  await act(async () => window.dispatchEvent(new CustomEvent("construpilot:draft-updated", { detail: { ...initial, revision: 1, body: "Version IA" } })));
  expect(container.querySelector("textarea").value).toBe("Ma correction non enregistrée");
  expect(container.querySelector('[role="alert"]').textContent).toContain("version plus récente");
  expect(button("Enregistrer").disabled).toBe(true);
});

test("enregistre avec la révision réellement affichée", async () => {
  api.put.mockResolvedValue({ data: { ...initial, revision: 1, body: "Correction" } });
  await mount(); await type("Correction"); await click("Enregistrer");
  expect(api.put).toHaveBeenCalledWith("/assistant/work-drafts/work_test", expect.objectContaining({ expected_revision: 0, body: "Correction" }));
  expect(container.textContent).toContain("Version 1");
  expect(container.textContent).not.toContain("modifications non enregistrées");
});

test("un conflit serveur conserve le texte sans réessayer l'écriture", async () => {
  api.put.mockRejectedValue({ response: { status: 409, data: { detail: "Version modifiée" } } });
  await mount(); await type("Ma proposition"); await click("Enregistrer");
  expect(api.put).toHaveBeenCalledTimes(1);
  expect(container.querySelector("textarea").value).toBe("Ma proposition");
  expect(button("Enregistrer").disabled).toBe(true);
});

test("reprendre une ancienne version ne réutilise pas son ancien numéro", async () => {
  api.get.mockImplementation(url => Promise.resolve({ data: url.endsWith("/versions") ? { versions: [{ ...initial, revision: 1, body: "Texte ancien" }] } : { ...initial, revision: 3 } }));
  api.put.mockResolvedValue({ data: { ...initial, revision: 4, body: "Texte ancien" } });
  await mount(); await click("Historique"); await click("Reprendre la version 1 — Objet"); await click("Enregistrer");
  expect(api.put).toHaveBeenCalledWith("/assistant/work-drafts/work_test", expect.objectContaining({ expected_revision: 3, body: "Texte ancien" }));
});

test("une réponse de chargement tardive ne remplace pas une révision plus récente", async () => {
  let resolve; api.get.mockImplementation(() => new Promise(r => { resolve = r; }));
  await mount();
  await act(async () => window.dispatchEvent(new CustomEvent("construpilot:draft-updated", { detail: { ...initial, revision: 2, body: "Version récente" } })));
  await act(async () => resolve({ data: { ...initial, revision: 1, body: "Ancienne version" } }));
  expect(container.querySelector("textarea").value).toBe("Version récente");
});
