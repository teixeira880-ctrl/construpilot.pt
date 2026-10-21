import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";

import { CadImportInfo, CadUnitPicker } from "../CadImportInfo";

const mockUseI18n = jest.fn();

jest.mock("@/context/I18nContext", () => ({
  useI18n: () => mockUseI18n(),
}));

global.IS_REACT_ACT_ENVIRONMENT = true;

let container;
let root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

const infoFixture = {
  complete: true,
  units: { name: "Millimetres" },
  layout: "Model",
  diagnostics: [{ code: "UNSUPPORTED_ENTITIES" }],
  conversion: {
    provider: "autodesk",
    engine: "Autodesk.AutoCAD+26_0",
    format_version: "AC1032",
    cached: true,
  },
};

test.each([
  ["pt", "Leitura CAD"],
  ["en", "CAD reading"],
  ["fr", "Lecture CAO"],
])("CadImportInfo renders translation and stable testids for %s", async (lang, title) => {
  mockUseI18n.mockReturnValue({ lang });

  await act(async () => {
    root.render(<CadImportInfo info={infoFixture} testId="cad-import-info" />);
  });

  expect(container.querySelector('[data-testid="cad-import-info-toggle"]').textContent).toContain(title);
  expect(container.querySelector('[data-testid="cad-import-info-provider"]').textContent).toContain("Autodesk AutoCAD");
  expect(container.querySelector('[data-testid="cad-import-info-engine"]').textContent).toContain("AutoCAD+26_0");
  expect(container.querySelector('[data-testid="cad-import-info-format"]').textContent).toContain("AC1032");
  expect(container.querySelector('[data-testid="cad-import-info-cached"]')).not.toBeNull();
  expect(container.querySelector('[data-testid="cad-import-info-diagnostic-0"]')).not.toBeNull();
});

test("CadUnitPicker keeps expected unit testids and actions", async () => {
  mockUseI18n.mockReturnValue({ lang: "en" });
  const onChoose = jest.fn();
  const onCancel = jest.fn();

  await act(async () => {
    root.render(<CadUnitPicker file={{ name: "public-line-2013.dwg" }} onChoose={onChoose} onCancel={onCancel} />);
  });

  ["mm", "cm", "m", "inches", "feet"].forEach((u) => {
    expect(container.querySelector(`[data-testid="cad-unit-${u}"]`)).not.toBeNull();
  });

  await act(async () => {
    container.querySelector('[data-testid="cad-unit-mm"]').click();
  });
  expect(onChoose).toHaveBeenCalledWith("mm");

  await act(async () => {
    container.querySelector('[data-testid="cad-unit-cancel"]').click();
  });
  expect(onCancel).toHaveBeenCalled();
});