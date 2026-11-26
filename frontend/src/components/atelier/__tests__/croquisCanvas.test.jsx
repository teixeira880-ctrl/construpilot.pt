/**
 * @jest-environment jsdom
 */
// Croquis à main levée : un trait de souris / doigt / stylet devient des points en mètres (1 m = ppm pixels),
// la cote demande sa longueur réelle, « Annuler » revient en arrière, et le bouton envoie {traits, textes, cotes, y_bas}.
import { act } from "react";
import { createRoot } from "react-dom/client";
import CroquisCanvas from "../CroquisCanvas";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function monter(props) {
  const div = document.createElement("div");
  document.body.appendChild(div);
  const root = createRoot(div);
  act(() => root.render(<CroquisCanvas {...props} />));
  const svg = div.querySelector("[data-testid=croquis-feuille]");
  svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: 900, height: 560 });
  return { div, root, svg };
}

function pointer(el, type, x, y) {
  const ev = new MouseEvent(type, { bubbles: true, clientX: x, clientY: y });
  Object.defineProperty(ev, "pointerId", { value: 1 });
  act(() => el.dispatchEvent(ev));
}

function trace(svg, pts) {
  pointer(svg, "pointerdown", ...pts[0]);
  pts.slice(1).forEach((p) => pointer(svg, "pointermove", ...p));
  pointer(svg, "pointerup", ...pts[pts.length - 1]);
}

test("un trait devient des points en mètres et part au redressement", () => {
  const onRedresser = jest.fn();
  const { div, svg } = monter({ onRedresser });
  trace(svg, [[36, 36], [100, 37], [180, 36], [360, 38]]);
  trace(svg, [[360, 38], [361, 200], [360, 396]]);
  expect(svg.querySelectorAll("path").length).toBe(2);
  act(() => div.querySelector("[data-testid=croquis-annuler]").click());
  expect(svg.querySelectorAll("path").length).toBe(1);
  act(() => div.querySelector("[data-testid=croquis-redresser]").click());
  expect(onRedresser).toHaveBeenCalledTimes(1);
  const body = onRedresser.mock.calls[0][0];
  expect(body.y_bas).toBe(true);
  expect(body.traits).toHaveLength(1);
  expect(body.traits[0].type).toBe("mur");
  expect(body.traits[0].points[0]).toEqual([1, 1]);          // 36 px = 1 m au zoom de départ
  expect(body.traits[0].points.at(-1)[0]).toBeCloseTo(10, 3);
});

test("outil cote : la longueur saisie part avec le croquis ; outil porte", () => {
  const onRedresser = jest.fn();
  const { div, svg } = monter({ onRedresser, lang: "pt" });
  trace(svg, [[0, 0], [360, 0]]);
  window.prompt = jest.fn(() => "12,5");
  act(() => div.querySelector("[data-testid=croquis-outil-cote]").click());
  trace(svg, [[0, 20], [360, 20]]);
  act(() => div.querySelector("[data-testid=croquis-outil-porte]").click());
  trace(svg, [[40, 0], [70, 0]]);
  act(() => div.querySelector("[data-testid=croquis-redresser]").click());
  const body = onRedresser.mock.calls[0][0];
  expect(body.cotes).toEqual([{ a: [0, 0.556], b: [10, 0.556], m: 12.5 }]);
  expect(body.traits.map((t) => t.type)).toEqual(["mur", "porte"]);
  expect(div.textContent).toContain("Endireitar");
});
