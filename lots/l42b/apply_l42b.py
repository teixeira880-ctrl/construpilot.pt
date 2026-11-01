"""Lot 42b — l'assistante ne devine plus les adresses : menu réel du site envoyé avec l'écran, page 404 signalée.
Usage : python3 apply_l42b.py /app"""
import sys, pathlib
root = pathlib.Path(sys.argv[1])
w = root / "frontend/src/components/admin/avatarScreenWatch.js"; s = w.read_text()
if "menuLinks" not in s:
    a = "function build() {"
    assert s.count(a) == 1, "ancre build"
    s = s.replace(a, '''// Pages réellement disponibles (menu latéral, barre du bas, liens internes visibles) : l'agent n'invente plus d'adresse.
function menuLinks() {
  const seen = new Map();
  document.querySelectorAll('nav a[href^="/"], aside a[href^="/"], header a[href^="/"], [data-testid^="workspace-nav"] a[href^="/"], a[data-testid^="workspace-"][href^="/"]').forEach((a) => {
    if (inDock(a)) return;
    const href = a.getAttribute("href").split("#")[0];
    const label = clean(a.getAttribute("aria-label") || a.innerText, 40);
    if (href && label && !seen.has(href)) seen.set(href, label);
  });
  return [...seen].slice(0, 80).map(([href, label]) => `${label}=${href}`);
}
const notFound = () => /\\b404\\b|p[áa]gina n[ãa]o encontrada|page (introuvable|non trouv[ée]e)|page not found/i.test(document.body.innerText.slice(0, 3000));
''' + a, 1)
    a = "    visible: viewportText(main),"
    assert s.count(a) == 1, "ancre visible"
    s = s.replace(a, a + "\n    not_found: notFound(),\n    menu: window.location.pathname !== lastPath ? menuLinks() : undefined,", 1)
    w.write_text(s)
p = root / "avatar_agent/agent.py"; s = p.read_text()
if "self.menu" not in s:
    a = "        self.latest = data\n"
    assert s.count(a) == 1, "ancre latest"
    s = s.replace(a, a + "        if data.get(\"menu\"):\n            self.menu = data[\"menu\"]\n", 1)
    a = "        self.pending_event: dict | None = None\n"
    assert s.count(a) == 1, "ancre pending"
    s = s.replace(a, a + "        self.menu: list = []\n", 1)
    a = "            text = render_screen(data or {})\n"
    assert s.count(a) == 1, "ancre render"
    s = s.replace(a, a + "            if self.menu:\n                text += \"\\nSITE PAGES (the ONLY valid paths for ui_navigate on this site — never invent one): \" + \", \".join(self.menu)[:2500]\n", 1)
    a = '    out = [f"Page: {s.get(\'path\', \'?\')}'
    assert s.count(a) == 1, "ancre page"
    s = s.replace(a, '    out = []\n    if s.get("not_found"):\n        out.append("THIS PAGE DOES NOT EXIST (404): go back (ui_back) and pick a real page from SITE PAGES, say so in one sentence.")\n    out += [f"Page: {s.get(\'path\', \'?\')}', 1)
    a = '        return "\\n".join(out)[:4200]'
    if a not in s:
        a = '    return "\\n".join(out)[:4200]'
    assert s.count(a) == 1, "ancre return"
    s = s.replace(a, a.replace("4200", "4600"), 1)
    a = "    \"(B) DATA THROUGH THE API"
    p.write_text(s)
print("L42b OK")
