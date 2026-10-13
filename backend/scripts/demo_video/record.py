"""Enregistrement d'écran animé (Playwright video) des scènes ConstruPilot — curseur visible, saisies, clics, scroll."""
import asyncio, json, os, sys, glob, shutil, time
from playwright.async_api import async_playwright

BASE = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()
LANG = os.environ.get("DEMO_LANG", "fr")
OUT = sys.argv[1] if len(sys.argv) > 1 else f"/app/backend/scripts/demo_video/work/clips{'_pt' if LANG == 'pt' else ''}"
ONLY = sys.argv[2].split(",") if len(sys.argv) > 2 else None
EMAIL, PWD = "pro@construpilot.fr", "Pro2026!"
CTX = json.loads(os.environ.get("CTX_IDS", "{}"))
W, H = 1920, 1080

CURSOR_JS = """
(() => {
  const c = document.createElement('div'); c.id = '__cur';
  c.style.cssText = 'position:fixed;z-index:2147483647;width:22px;height:22px;pointer-events:none;left:-50px;top:-50px;'
    + 'transform:translate(-4px,-2px);transition:transform .08s;';
  c.innerHTML = '<svg width="22" height="22" viewBox="0 0 24 24"><path d="M5 3l14 8-6 1.5L9.5 19z" fill="#fff" stroke="#04120a" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  const r = document.createElement('div'); r.id = '__ring';
  r.style.cssText = 'position:fixed;z-index:2147483646;width:34px;height:34px;border-radius:50%;border:3px solid #a3e635;'
    + 'pointer-events:none;left:-50px;top:-50px;opacity:0;transform:translate(-17px,-17px) scale(.4);transition:opacity .35s,transform .35s;';
  const add = () => { if (document.body) { document.body.appendChild(c); document.body.appendChild(r); } else setTimeout(add, 20); };
  add();
  window.__mv = (x, y) => { c.style.left = x + 'px'; c.style.top = y + 'px'; r.style.left = x + 'px'; r.style.top = y + 'px'; };
  window.__dn = () => { c.style.transform = 'translate(-4px,-2px) scale(.85)'; r.style.opacity = '1'; r.style.transform = 'translate(-17px,-17px) scale(1.4)';
    setTimeout(() => { c.style.transform = 'translate(-4px,-2px)'; r.style.opacity = '0'; r.style.transform = 'translate(-17px,-17px) scale(.4)'; }, 350); };
})();
"""


class Actor:
    def __init__(self, page):
        self.p = page
        self.x, self.y = W * 0.55, H * 0.5

    async def _sync(self):
        try:
            await self.p.evaluate(f"window.__mv && window.__mv({self.x}, {self.y})")
        except Exception:
            pass

    async def move(self, x, y, ms=700):
        steps = max(8, int(ms / 16))
        for i in range(1, steps + 1):
            t = i / steps
            e = t * t * (3 - 2 * t)
            cx, cy = self.x + (x - self.x) * e, self.y + (y - self.y) * e
            await self.p.mouse.move(cx, cy)
            try:
                await self.p.evaluate(f"window.__mv && window.__mv({cx}, {cy})")
            except Exception:
                pass
            await self.p.wait_for_timeout(16)
        self.x, self.y = x, y

    async def click(self, sel, ms=700, timeout=8000):
        loc = self.p.locator(sel).first
        await loc.wait_for(state="visible", timeout=timeout)
        await loc.scroll_into_view_if_needed()
        await self.p.wait_for_timeout(250)
        b = await loc.bounding_box()
        if not b:
            return
        await self.move(b["x"] + b["width"] / 2, b["y"] + min(b["height"] / 2, 30), ms)
        await self.p.evaluate("window.__dn && window.__dn()")
        await self.p.mouse.down(); await self.p.wait_for_timeout(90); await self.p.mouse.up()
        await self.p.wait_for_timeout(350)

    async def type(self, sel, text, delay=45):
        await self.click(sel)
        await self.p.locator(sel).first.fill("")
        await self.p.keyboard.type(text, delay=delay)
        await self.p.wait_for_timeout(400)

    async def select(self, sel, value):
        await self.click(sel)
        await self.p.locator(sel).first.select_option(value)
        await self.p.wait_for_timeout(500)

    async def scroll(self, px, ms=1400):
        steps = max(10, int(ms / 40))
        for _ in range(steps):
            await self.p.mouse.wheel(0, px / steps)
            await self.p.wait_for_timeout(40)
        await self.p.wait_for_timeout(500)

    async def hover_path(self, points, ms=600):
        for x, y in points:
            await self.move(x, y, ms)


async def s_landing(a, p):
    await p.wait_for_timeout(1800); await a.scroll(700, 2200); await a.scroll(700, 2200); await a.move(W * 0.5, H * 0.6, 600)

async def s_estimation_form(a, p):
    await p.wait_for_timeout(1200)
    await a.click('[data-testid="select-project-type"]'); await p.wait_for_timeout(700)
    try:
        opt = p.locator('[role="option"]', has_text="Piscin").first
        await opt.scroll_into_view_if_needed(timeout=3000); await p.wait_for_timeout(400)
        await a.click('[role="option"]:has-text("Piscin")', ms=600, timeout=3000)
    except Exception:
        await p.keyboard.type("Piscin", delay=80); await p.keyboard.press("Enter")
    await a.type('[data-testid="input-surface"]', "32", delay=140)
    await p.wait_for_timeout(600)
    await a.click('[data-testid="wizard-next-btn"]'); await p.wait_for_timeout(900)

async def s_estimation_result(a, p):
    await p.wait_for_timeout(1000)
    await a.click('[data-testid="wizard-next-btn"]'); await p.wait_for_timeout(700)
    await a.click('[data-testid="wizard-next-btn"]'); await p.wait_for_timeout(700)
    await a.click('[data-testid="wizard-compute-btn"]')
    await p.wait_for_timeout(4500)
    await a.scroll(500, 1800); await a.scroll(600, 2000)

async def s_piscine_result(a, p):
    await p.wait_for_timeout(1000)
    await a.click('[data-testid="wizard-next-btn"]'); await p.wait_for_timeout(600)
    await a.click('[data-testid="wizard-next-btn"]'); await p.wait_for_timeout(600)
    await a.click('[data-testid="wizard-compute-btn"]')
    await p.wait_for_timeout(4500)
    try:
        await p.locator('[data-testid="pool-items-card"]').scroll_into_view_if_needed(timeout=8000)
    except Exception:
        pass
    await p.wait_for_timeout(600); await a.scroll(500, 2200)
    try:
        b = await p.locator('[data-testid="pool-create-quote-btn"]').bounding_box()
        if b:
            await a.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 900)
    except Exception:
        pass
    await p.wait_for_timeout(800)

async def s_smart_project(a, p):
    await p.wait_for_timeout(1200)
    txt = ("Remodelar uma casa de banho de 8 m²: remoção do azulejo, base de duche, azulejo nas paredes, móvel de lavatório e pintura do teto."
           if LANG == "pt" else
           "Rénover une salle de bain de 8 m² : dépose du carrelage, douche à l'italienne, faïence murale, meuble vasque et peinture du plafond.")
    await a.type('[data-testid="smart-project-input"]', txt, delay=28)
    await p.wait_for_timeout(500)
    b = await p.locator('[data-testid="smart-project-submit-btn"]').bounding_box()
    if b:
        await a.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, 800)
    await p.wait_for_timeout(1200)

async def s_calculateurs(a, p):
    await p.wait_for_timeout(1200)
    tabs = p.locator('[data-testid^="calculator-tab-"]')
    n = await tabs.count()
    if n > 1:
        await a.click(f'[data-testid^="calculator-tab-"] >> nth={min(1, n-1)}')
    await p.wait_for_timeout(700)
    inputs = p.locator('[data-testid="calculator-form"] input[type="number"]')
    k = await inputs.count()
    for i, val in zip(range(min(k, 2)), ["24", "3"]):
        await a.type(f'[data-testid="calculator-form"] input[type="number"] >> nth={i}', val, delay=120)
    try:
        await a.click('[data-testid="calculate-btn"]')
    except Exception:
        pass
    await p.wait_for_timeout(1500); await a.scroll(450, 1500)

async def s_prix(a, p):
    await p.wait_for_timeout(1200)
    await a.type('[data-testid="price-search-input"]', "azulejo" if LANG == "pt" else "carrelage", delay=90)
    try:
        await a.click('[data-testid="price-search-btn"]')
    except Exception:
        await p.keyboard.press("Enter")
    await p.wait_for_timeout(2500); await a.scroll(400, 1500)

async def s_photo(a, p):
    await p.wait_for_timeout(1500); await a.scroll(500, 1800); await a.scroll(-300, 1200)

async def s_devis_editeur(a, p):
    await p.wait_for_selector('[data-testid="editor-library-mode-select"]', timeout=25000)
    await p.wait_for_timeout(1500)
    await a.select('[data-testid="editor-library-mode-select"]', "company_first")
    await p.wait_for_timeout(500)
    await a.select('[data-testid="editor-library-mode-select"]', "shared_first")
    await a.scroll(500, 1600)
    try:
        await a.click('[data-testid="editor-add-line"]'); await p.wait_for_timeout(700)
    except Exception:
        pass
    await a.scroll(500, 1600)
    try:
        b = await p.locator('[data-testid="editor-totals"]').bounding_box()
        if b:
            await a.move(b["x"] + b["width"] / 2, b["y"] + 20, 800)
    except Exception:
        pass
    await p.wait_for_timeout(1000)

async def s_bibliotheque(a, p):
    await p.wait_for_selector('[data-testid="library-search-input"]', timeout=25000)
    await p.wait_for_timeout(800)
    await a.type('[data-testid="library-search-input"]', "pintura" if LANG == "pt" else "peinture", delay=90)
    await p.wait_for_timeout(1200); await a.scroll(400, 1500)

async def s_devis_suivi(a, p):
    await p.wait_for_timeout(1500); await a.hover_path([(W * 0.5, H * 0.45), (W * 0.5, H * 0.6)], 700); await a.scroll(500, 1800)

async def s_generic_scroll(a, p):
    await p.wait_for_timeout(1500); await a.scroll(600, 2000); await a.scroll(400, 1600)

async def s_plan(a, p):
    await p.wait_for_timeout(5000)
    for sel in ['[data-testid="tab-rooms"]', '[data-testid="recap-see-rooms"]']:
        try:
            await a.click(sel, timeout=4000); await p.wait_for_timeout(900); break
        except Exception:
            continue
    await a.hover_path([(W * 0.45, H * 0.45), (W * 0.6, H * 0.55), (W * 0.5, H * 0.65)], 700)
    await p.wait_for_timeout(800)

async def s_radar(a, p):
    await p.wait_for_timeout(5000)
    try:
        m = p.locator('[data-testid="radar-map"]')
        b = await m.bounding_box()
        if b:
            cx, cy = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
            await a.move(cx, cy, 600)
            await p.mouse.down(); await a.move(cx - 220, cy + 90, 1200); await p.mouse.up()
            await p.wait_for_timeout(1200)
    except Exception:
        pass
    try:
        await a.click('[data-testid="radar-list"] button, [data-testid="radar-list"] [role=button], [data-testid="radar-list"] li', timeout=4000)
        await p.wait_for_timeout(1500)
    except Exception:
        pass

async def s_rentabilite(a, p):
    await p.wait_for_selector('[data-testid="profit-include-open"]', timeout=25000)
    await p.wait_for_timeout(800)
    await a.click('[data-testid="profit-include-open"]'); await p.wait_for_timeout(1200)
    try:
        await a.click('[data-testid^="profit-job-toggle-"]'); await p.wait_for_timeout(1500)
        await a.scroll(300, 1000)
    except Exception:
        pass

async def s_tarifs(a, p):
    await p.wait_for_timeout(1500)
    try:
        await a.click('[data-testid="pricing-tab-pro"]'); await p.wait_for_timeout(1200)
    except Exception:
        pass
    await a.scroll(500, 1800)

ANON = {"landing"}
SCENES = [
    ("landing", "/", s_landing),
    ("estimation_form", "/estimation", s_estimation_form),
    ("estimation_result", "/estimation?type=renovation_complete&surface=120", s_estimation_result),
    ("piscine_result", "/estimation?type=piscine_beton&surface=32", s_piscine_result),
    ("smart_project", "/smart-project", s_smart_project),
    ("calculateurs", "/calculateurs", s_calculateurs),
    ("prix", "/prix", s_prix),
    ("photo", "/photo", s_photo),
    ("devis_editeur", "/devis-editeur/{DOC}", s_devis_editeur),
    ("bibliotheque", "/bibliotheque", s_bibliotheque),
    ("devis_suivi", "/devis", s_devis_suivi),
    ("factures", "/factures", s_generic_scroll),
    ("clients", "/clients", s_generic_scroll),
    ("plan", "/plan?open={PLAN}", s_plan),
    ("etudes_pc", "/pc", s_generic_scroll),
    ("appro", "/appro", s_generic_scroll),
    ("radar", "/radar", s_radar),
    ("rentabilite", "/rentabilite", s_rentabilite),
    ("suivi_chantier", "/suivi-chantier", s_generic_scroll),
    ("rendu_ia", "/rendu-ia", s_generic_scroll),
    ("blog", "/blog", s_generic_scroll),
    ("tarifs", "/tarifs", s_tarifs),
    ("fonctionnalites", "/fonctionnalites", s_generic_scroll),
]


async def run():
    os.makedirs(OUT, exist_ok=True)
    tmp = "/app/backend/scripts/demo_video/work/rec_tmp"
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        # Connexion via l'API (évite le formulaire) puis injection du jeton dans le navigateur
        import httpx
        from urllib.parse import urlparse
        r = httpx.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PWD}, timeout=30)
        r.raise_for_status()
        token = r.json()["token"]
        host = urlparse(BASE).hostname
        cookies = [{"name": "session_token", "value": r.cookies.get("session_token") or token, "domain": host, "path": "/",
                    "httpOnly": True, "secure": True, "sameSite": "Lax", "expires": time.time() + 6 * 24 * 3600}]
        ls = [{"name": "construpilot_token", "value": token},
              {"name": "cp_cookie_consent", "value": json.dumps({"analytics": True, "ads": True, "ts": int(time.time() * 1000)})},
              {"name": "construpilot_lang", "value": LANG}]
        httpx.put(f"{BASE}/api/auth/language", json={"lang": LANG}, headers={"Authorization": f"Bearer {token}"}, timeout=30)
        state = {"cookies": cookies, "origins": [{"origin": BASE, "localStorage": ls}]}
        anon_state = {"cookies": [], "origins": [{"origin": BASE, "localStorage": ls[1:]}]}
        print("login api ok")
        meta_path = f"{OUT}/meta.json"
        meta = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
        for slug, url, fn in SCENES:
            if ONLY and slug not in ONLY:
                continue
            url = url.replace("{DOC}", CTX.get("doc", "")).replace("{PLAN}", CTX.get("plan", ""))
            shutil.rmtree(tmp, ignore_errors=True)
            c = await browser.new_context(viewport={"width": W, "height": H}, locale="fr-FR",
                                          storage_state=anon_state if slug in ANON else state,
                                          record_video_dir=tmp, record_video_size={"width": W, "height": H})
            await c.add_init_script(CURSOR_JS)
            t0 = time.time()
            pg = await c.new_page()
            try:
                await pg.goto(BASE + url, wait_until="domcontentloaded")
                await pg.wait_for_timeout(1200)
                try:
                    await pg.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                try:
                    await pg.wait_for_function("document.body && document.body.innerText.length > 300", timeout=25000)
                except Exception:
                    pass
                await pg.wait_for_timeout(700)
                meta[slug] = round(time.time() - t0 + 0.2, 2)
                try:
                    await pg.evaluate("document.querySelectorAll('[data-sonner-toaster]').forEach(e=>e.style.display='none')")
                except Exception:
                    await pg.wait_for_timeout(1500)
                a = Actor(pg)
                await a.move(W * 0.55, H * 0.5, 300)
                await fn(a, pg)
                await pg.wait_for_timeout(800)
                print("ok", slug)
            except Exception as e:  # noqa: BLE001
                print("WARN", slug, type(e).__name__, str(e)[:100], "url=", pg.url)
                try:
                    await pg.screenshot(path=f"{OUT}/{slug}_fail.png")
                except Exception:
                    pass
            await c.close()
            vids = glob.glob(f"{tmp}/*.webm")
            if vids:
                shutil.move(vids[0], f"{OUT}/{slug}.webm")
            json.dump(meta, open(meta_path, "w"))
        await browser.close()
        httpx.put(f"{BASE}/api/auth/language", json={"lang": "fr"}, headers={"Authorization": f"Bearer {token}"}, timeout=30)


asyncio.run(run())
