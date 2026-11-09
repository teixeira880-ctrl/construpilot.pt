// Teste de integração da página (sem dependências extra: react-dom + act, como os testes existentes).
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import BimStudio from "@/pages/BimStudio";

const VERSION = {
  model_id: "bim_1", version: 1, status: "done", schema: "IFC4", chunks: 1, filename: "moradia.ifc",
  stats: { elements: 2, by_category: { paredes: 1, lajes: 1 }, with_missing: 0 },
  storeys: [{ gid: "s0", name: "Piso 0" }], warnings: [],
};
const ELEMENT = {
  gid: "w1", name: "Parede Norte", category: "paredes", category_label: "Paredes", storey: "Piso 0", storey_gid: "s0",
  ifc_class: "IfcWall", primary_key: "area", included: true, counted: true, missing: [], materials: ["Bloco"],
  properties: { Pset_WallCommon: { FireRating: "EI60" } },
  quantities: { area: { key: "area", value: 28, unit: "m²", origin: "declared", label: "Área", verified: false, source: "Qto" } },
};

jest.mock("@/lib/api", () => {
  const get = jest.fn((url) => {
    if (url === "/bim/config") return Promise.resolve({ data: { enabled: true, profile: "simples", max_upload_mb: 200, categories: { paredes: "Paredes", lajes: "Lajes" } } });
    if (url === "/bim/models") return Promise.resolve({ data: { items: [{ model_id: "bim_1", name: "Moradia", latest_version: 1, latest: VERSION }] } });
    if (url === "/bim/models/bim_1") return Promise.resolve({ data: { model_id: "bim_1", name: "Moradia", versions: [VERSION] } });
    if (url.includes("/elements/w1")) return Promise.resolve({ data: ELEMENT });
    if (url.includes("/elements")) return Promise.resolve({ data: { total: 1, items: [ELEMENT] } });
    return Promise.resolve({ data: {} });
  });
  return { api: { get, post: jest.fn(), put: jest.fn(() => Promise.resolve({ data: {} })), patch: jest.fn() },
           eur2: (v) => `${v} €`, eur: (v) => `${v} €`, num: (v) => String(v) };
});
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

const flush = async (n = 6) => { for (let i = 0; i < n; i += 1) await act(async () => { await Promise.resolve(); }); };
const byTestId = (id) => document.querySelector(`[data-testid="${id}"]`);

test("página BIM Studio: modo simples, lista de modelos, 3D sem WebGL e medições", async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  jest.spyOn(console, "error").mockImplementation(() => {}); // THREE avisa que o jsdom não tem WebGL
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(<MemoryRouter><BimStudio /></MemoryRouter>); });
  await flush();
  expect(host.textContent).toContain("BIM Studio");
  expect(byTestId("bim-simple-steps")).not.toBeNull();
  const modelBtn = [...host.querySelectorAll("button")].find((b) => b.textContent.includes("Moradia"));
  await act(async () => { modelBtn.click(); });
  await flush();
  // jsdom não tem WebGL → mensagem de recurso, a página continua utilizável
  expect(byTestId("bim-viewer-nogl")).not.toBeNull();
  await act(async () => { byTestId("bim-tab-medicoes").click(); });
  await flush();
  expect(byTestId("bim-measurements").textContent).toContain("Parede Norte");
  expect(byTestId("bim-measurements").textContent).toContain("Declarada");
  expect(host.textContent).not.toContain("IfcWall"); // modo simples esconde a terminologia IFC
  await act(async () => root.unmount());
});
