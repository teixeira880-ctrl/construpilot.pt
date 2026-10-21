/* iter149: PermissionContext fail-closed + generation/offline behavior tests */
import React from "react";
import { createRoot } from "react-dom/client";
import { act } from "react";

import { PermissionProvider, usePermissions } from "./PermissionContext";
import { api } from "../lib/api";

let mockUser = null;

jest.mock("../lib/api", () => ({
  api: { get: jest.fn() },
}));

jest.mock("./AuthContext", () => ({
  useAuth: () => ({ user: mockUser }),
}));

function Probe() {
  const p = usePermissions();
  return (
    <div>
      <div id="role">{String(p.role)}</div>
      <div id="loading">{String(p.loading)}</div>
      <div id="error">{String(p.error)}</div>
      <div id="active">{String(p.active)}</div>
      <div id="can-dashboard">{String(p.can("dashboard"))}</div>
      <div id="can-devis">{String(p.can("devis"))}</div>
    </div>
  );
}

function mount() {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const renderTree = () => root.render(<PermissionProvider><Probe /></PermissionProvider>);
  act(() => renderTree());
  return {
    host,
    rerender: () => act(() => renderTree()),
    text: (id) => host.querySelector(`#${id}`)?.textContent,
    cleanup: () => act(() => root.unmount()),
  };
}

async function eventually(assertion, timeoutMs = 3000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    await act(async () => { await new Promise((r) => setTimeout(r, 25)); });
    try {
      assertion();
      return;
    } catch {
      // retry
    }
  }
  assertion();
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  jest.resetAllMocks();
  mockUser = { user_id: "u_1", account_type: "pro", role: "user" };
});

afterEach(() => {
  document.body.innerHTML = "";
});

test("503/network style failure -> fail-closed error state", async () => {
  api.get.mockRejectedValueOnce(new Error("network failed"));
  const ui = mount();
  await eventually(() => expect(ui.text("error")).toBe("true"));
  expect(ui.text("can-dashboard")).toBe("false");
  ui.cleanup();
});

test("malformed payload (missing active boolean) -> fail-closed", async () => {
  api.get.mockResolvedValueOnce({ data: { role: "owner", permissions: { dashboard: true }, in_org: true } });
  const ui = mount();
  await eventually(() => expect(ui.text("error")).toBe("true"));
  expect(ui.text("can-dashboard")).toBe("false");
  ui.cleanup();
});

test("missing expected permission booleans and unknown keys stay denied", async () => {
  api.get.mockResolvedValueOnce({ data: { role: "owner", active: true, permissions: { unknown_key: true }, in_org: true } });
  const ui = mount();
  await eventually(() => expect(ui.text("loading")).toBe("false"));
  expect(ui.text("error")).toBe("false");
  expect(ui.text("can-dashboard")).toBe("false");
  expect(ui.text("can-devis")).toBe("false");
  ui.cleanup();
});

test("stale delayed permissions from previous account are ignored", async () => {
  let resolveFirst;
  api.get
    .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; }))
    .mockResolvedValueOnce({
      data: { role: "member", active: true, permissions: { dashboard: true }, in_org: true },
    });

  const ui = mount();
  mockUser = { user_id: "u_2", account_type: "pro", role: "user" };
  ui.rerender();

  await eventually(() => expect(ui.text("role")).toBe("member"));
  expect(ui.text("can-devis")).toBe("false");

  await act(async () => {
    resolveFirst({
      data: { role: "owner", active: true, permissions: { dashboard: true, devis: true }, in_org: true },
    });
  });
  await eventually(() => expect(ui.text("role")).toBe("member"));
  expect(ui.text("can-devis")).toBe("false");
  ui.cleanup();
});

test("offline clears permissions UI; online refresh restores", async () => {
  api.get.mockResolvedValueOnce({
    data: { role: "owner", active: true, permissions: { dashboard: true, devis: true }, in_org: true },
  });
  const ui = mount();
  await eventually(() => expect(ui.text("can-dashboard")).toBe("true"));

  await act(async () => {
    window.dispatchEvent(new Event("offline"));
  });
  await eventually(() => expect(ui.text("error")).toBe("true"));

  expect(ui.text("can-dashboard")).toBe("false");

  api.get.mockResolvedValueOnce({
    data: { role: "owner", active: true, permissions: { dashboard: true, devis: true }, in_org: true },
  });
  await act(async () => {
    window.dispatchEvent(new Event("online"));
  });
  await eventually(() => expect(ui.text("can-dashboard")).toBe("true"));
  ui.cleanup();
});

test("particulier user bypasses company API and remains fail-closed", async () => {
  mockUser = { user_id: "p_1", account_type: "particulier", role: "user" };
  const ui = mount();
  await eventually(() => expect(ui.text("loading")).toBe("false"));
  expect(api.get).not.toHaveBeenCalled();
  expect(ui.text("active")).toBe("true");
  expect(ui.text("can-dashboard")).toBe("false");
  ui.cleanup();
});
