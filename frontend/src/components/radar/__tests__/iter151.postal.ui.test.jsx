import React, { act } from "react";
import { createRoot } from "react-dom/client";

import PostalSendDialog from "../PostalSendDialog";
import { PostalOffer, usePostalOffer } from "../PostalOffer";
import { PostalPriceConsent } from "../PostalPriceConsent";
import { usePostalQuote } from "../usePostalQuote";
import { api } from "@/lib/api";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), post: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock("react-router-dom", () => ({ Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a> }), { virtual: true });
jest.mock("@/context/AuthContext", () => ({ useAuth: jest.fn() }));
jest.mock("../usePostalQuote", () => ({ usePostalQuote: jest.fn(), postalError: jest.fn(() => "Postal error") }));
jest.mock("../PostalOffer", () => {
  const actual = jest.requireActual("../PostalOffer");
  return { ...actual, usePostalOffer: jest.fn() };
});
jest.mock("../postalCopy", () => ({
  usePostalCopy: () => (key) => ({
    demo: "Demo one free company letter",
    checking: "checking",
    offerError: "offer error",
    retry: "Retry",
    available: "Your free letter is available.",
    used: "Free letter used",
    pending: "Pending/Reserved",
    future: "20 € HT · Stripe disabled",
    amount: "Amount",
    free: "0,00 € · offert",
    unavailable: "Indisponible",
    calculating: "Calculating",
    noCharge: "No card required",
    consent: "Consent OK",
    validRequired: "Need valid quote",
    refresh: "Refresh",
    send: "Envoyer gratuitement",
    diagnosis: "Admin diagnostics",
    costCovered: "Cost covered",
  }[key] || key),
}));
jest.mock("@/components/ui/dialog", () => ({
  Dialog: ({ open, children }) => open ? <div data-testid="dialog-open">{children}</div> : null,
  DialogContent: ({ children, overlayClassName, ...props }) => <div data-overlay-class={overlayClassName} {...props}>{children}</div>,
  DialogHeader: ({ children }) => <div>{children}</div>,
  DialogTitle: ({ children, ...props }) => <h2 {...props}>{children}</h2>,
  DialogDescription: ({ children, ...props }) => <p {...props}>{children}</p>,
}));

jest.mock("../PostalDestination", () => ({
  PostalDestination: ({ destination, onChange }) => (
    <div>
      <button data-testid="dest-contact" onClick={() => onChange("contact")}>contact</button>
      <button data-testid="dest-terrain" onClick={() => onChange("terrain")}>terrain</button>
      <span data-testid="dest-current">{destination}</span>
    </div>
  ),
}));

global.IS_REACT_ACT_ENVIRONMENT = true;

const { useAuth } = require("@/context/AuthContext");

const opp = {
  id: "opp_1",
  commune: "Paris",
  cp: "75001",
  adresse: "10 rue de Rivoli",
  promoteur: { nom: "Dest", adresse1: "10 rue de Rivoli", cp: "75001", ville: "Paris" },
};
const campaign = { token: "rop_iter151" };

let container;
let root;

const flush = async () => act(async () => { await Promise.resolve(); });

beforeEach(() => {
  jest.resetAllMocks();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  api.get.mockResolvedValue({ data: { sends: [] } });
  api.post.mockResolvedValue({ data: {} });
  useAuth.mockReturnValue({ user: { user_id: "u1", organization_id: "org1", role: "user" } });
  usePostalOffer.mockReturnValue({
    offer: { eligible: true, status: "available", phase: "demo", customer_amount_cents: 0 },
    loading: false,
    error: false,
    refresh: jest.fn(),
  });
  usePostalQuote.mockImplementation(({ mode, form, valid }) => ({
    price: valid ? {
      quote_id: `q-${mode}-${form.adresse1}`,
      offer: { phase: "demo", eligible: true, customer_amount_cents: 0 },
      expires_at: new Date(Date.now() + 10 * 60 * 1000).toISOString(),
    } : null,
    error: null,
    errorCode: null,
    loading: false,
    refresh: jest.fn(),
  }));
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

const renderDialog = async (props = {}) => {
  await act(async () => {
    root.render(<PostalSendDialog open onClose={jest.fn()} campaign={campaign} opp={opp} {...props} />);
  });
  await flush();
};

test("PostalOffer available state shows remaining and future inactive price", async () => {
  await act(async () => {
    root.render(<PostalOffer offer={{ eligible: true, status: "available" }} loading={false} error={false} refresh={jest.fn()} />);
  });
  expect(container.querySelector('[data-testid="postal-offer-remaining"]').textContent).toContain("available");
  expect(container.querySelector('[data-testid="postal-future-price"]').textContent).toContain("20 € HT");
});

test("PostalPriceConsent shows 0EUR and no-charge consent line", async () => {
  await act(async () => {
    root.render(<PostalPriceConsent
      price={{ offer: { phase: "demo", eligible: true, customer_amount_cents: 0 } }}
      error={null}
      loading={false}
      refresh={jest.fn()}
      checked={false}
      onCheck={jest.fn()}
      busy={false}
    />);
  });
  expect(container.querySelector('[data-testid="postal-price-total"]').textContent).toContain("0,00");
  expect(container.querySelector('[data-testid="postal-no-charge"]').textContent).toContain("No card required");
});

test("eligible quote allows send button after consent without triggering real send", async () => {
  await renderDialog();
  const sendBtn = container.querySelector('[data-testid="postal-send-btn"]');
  const consent = container.querySelector('[data-testid="postal-price-consent"]');
  expect(sendBtn.disabled).toBe(true);
  await act(async () => consent.click());
  expect(sendBtn.disabled).toBe(false);
  expect(api.post).not.toHaveBeenCalled();
});

test("address or mode change invalidates consent and disables send again", async () => {
  await renderDialog();
  const consent = container.querySelector('[data-testid="postal-price-consent"]');
  const sendBtn = container.querySelector('[data-testid="postal-send-btn"]');
  await act(async () => consent.click());
  expect(sendBtn.disabled).toBe(false);

  const mode = container.querySelector('[data-testid="postal-mode"]');
  await act(async () => {
    mode.value = "suivi";
    mode.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await flush();
  expect(sendBtn.disabled).toBe(true);
});

test("reserved/exhausted offer blocks send button", async () => {
  usePostalOffer.mockReturnValue({
    offer: { eligible: false, status: "reserved", phase: "demo", customer_amount_cents: 0 },
    loading: false,
    error: false,
    refresh: jest.fn(),
  });
  await renderDialog();
  expect(container.querySelector('[data-testid="postal-offer-remaining"]').textContent).toContain("Pending/Reserved");
  expect(container.querySelector('[data-testid="postal-send-btn"]').disabled).toBe(true);
});

test("quote IP error blocks flow and admin link is admin-only", async () => {
  usePostalQuote.mockReturnValue({
    price: null,
    error: "IP error",
    errorCode: "INVALID_TOKEN_FOR_IP",
    loading: false,
    refresh: jest.fn(),
  });

  useAuth.mockReturnValue({ user: { user_id: "u1", organization_id: "org1", role: "admin" } });
  await renderDialog();
  expect(container.querySelector('[data-testid="postal-quote-error"]').textContent).toContain("IP error");
  expect(container.querySelector('[data-testid="postal-admin-diagnostics-link"]')).not.toBeNull();
  expect(container.querySelector('[data-testid="postal-send-btn"]').disabled).toBe(true);

  useAuth.mockReturnValue({ user: { user_id: "u1", organization_id: "org1", role: "user" } });
  await renderDialog();
  expect(container.querySelector('[data-testid="postal-admin-diagnostics-link"]')).toBeNull();
});

test("history retry appears on load failure and recovers after successful refresh", async () => {
  api.get
    .mockRejectedValueOnce(new Error("history down"))
    .mockResolvedValueOnce({ data: { sends: [], refresh_error: "" } });

  await renderDialog();
  expect(container.querySelector('[data-testid="postal-history-error"]')).not.toBeNull();
  const retry = container.querySelector('[data-testid="postal-history-retry"]');
  expect(retry).not.toBeNull();

  await act(async () => retry.click());
  await flush();
  expect(container.querySelector('[data-testid="postal-history-error"]')).toBeNull();
});

test("renders safely at 320 and 390 widths", async () => {
  window.innerWidth = 320;
  await renderDialog();
  expect(container.querySelector('[data-testid="postal-dialog"]')).not.toBeNull();

  window.innerWidth = 390;
  await renderDialog();
  expect(container.querySelector('[data-testid="postal-dialog"]')).not.toBeNull();
});
