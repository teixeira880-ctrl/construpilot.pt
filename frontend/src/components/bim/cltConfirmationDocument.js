import { confirmationScript, confirmationTemplate } from "./cltConfirmationAssets";

const FRAME_STYLE = String.raw`
  :root{color-scheme:light dark;--foreground:light-dark(#183129,#eef5f0);--background:light-dark(#fff,#16201c);--muted-foreground:light-dark(#4b6258,#b4c7bd);--primary:light-dark(#14583e,#99daba);--green:light-dark(#167753,#66c89c);--blue:light-dark(#1467a5,#8ccaff);--orange:light-dark(#ae510c,#efaa68);--line:light-dark(#d5e2d9,#3c5045)}
  *{box-sizing:border-box}
  body{font:15px/1.45 system-ui,sans-serif;color:var(--foreground);background:var(--background);margin:0;padding:12px;overflow-wrap:anywhere}
  h2,h3,p{margin:0}h2{font-size:1.32em}h3{font-size:1.07em}
  .viz-row{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center}
  .table-responsive{overflow-x:auto}.table{width:100%;border-collapse:collapse;text-align:left}.table :is(th,td){padding:7px;border-bottom:1px solid var(--line);vertical-align:top}
  .text-small{font-size:.9em;color:var(--muted-foreground)}
  .form-label{display:grid;gap:4px;min-width:0}
  :is(.form-control,.form-select,.btn){font:inherit;color:inherit;background:var(--background);border:1px solid var(--line);border-radius:7px;padding:7px 10px;min-height:42px;max-width:100%}
  .form-control,.form-select{width:100%}.btn{cursor:pointer}
  .btn-primary{background:var(--primary);color:var(--background);border-color:var(--primary)}
  .btn[aria-pressed=true]{border-color:var(--primary);font-weight:600}
  :focus-visible{outline:2px solid var(--primary);outline-offset:2px}
`;

const RESIZE_SCRIPT = String.raw`
  (() => {
    if (typeof ResizeObserver !== "function") return;
    const root = document.getElementById("home-a-confirm");
    new ResizeObserver(() => {
      parent.postMessage({ type: "clt-confirmation-height", height: Math.ceil(root.getBoundingClientRect().height + 24) }, "*");
    }).observe(root);
  })();
`;

export function confirmationDocument(pages) {
  const data = JSON.stringify(pages).replace(/</g, "\\u003c");
  const fragment = confirmationTemplate
    .replace("__EVIDENCE_PAYLOAD__", () => data)
    .replace("__CONFIRMATION_SCRIPT__", () => confirmationScript);
  return '<!doctype html><html lang="pt-PT"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'unsafe-inline\'; style-src \'unsafe-inline\'; img-src data:; form-action \'none\'; base-uri \'none\'">' +
    '<title>Confirmação de medições CLT</title><style>' + FRAME_STYLE + '</style><body>' + fragment +
    '<script>' + RESIZE_SCRIPT + '</script></body></html>';
}
