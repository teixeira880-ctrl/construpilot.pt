"""Capture des écrans réels de ConstruPilot (Playwright) pour la vidéo de démonstration."""
import asyncio, os, sys, json
from playwright.async_api import async_playwright

BASE = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()
OUT = sys.argv[1] if len(sys.argv) > 1 else "/app/backend/scripts/demo_video/work/shots"
EMAIL, PWD = "pro@construpilot.fr", "Pro2026!"

# (slug, url, actions) — actions = liste de (kind, arg)
SCENES = [
    ("landing", "/", [("wait", 2500)]),
    ("estimation_form", "/estimation?type=piscine_beton&surface=32", [("wait", 2000)]),
    ("estimation_result", "/estimation?type=renovation_complete&surface=120", [("click", '[data-testid="wizard-next-btn"]'), ("wait", 600), ("click", '[data-testid="wizard-next-btn"]'), ("wait", 600), ("click", '[data-testid="wizard-compute-btn"]'), ("wait", 5000)]),
    ("piscine_result", "/estimation?type=piscine_beton&surface=32", [("click", '[data-testid="wizard-next-btn"]'), ("wait", 600), ("click", '[data-testid="wizard-next-btn"]'), ("wait", 600), ("click", '[data-testid="wizard-compute-btn"]'), ("wait", 5000), ("scroll", '[data-testid="pool-items-card"]'), ("wait", 800)]),
    ("smart_project", "/smart-project", [("wait", 2500)]),
    ("calculateurs", "/calculateurs", [("wait", 2500)]),
    ("prix", "/prix", [("wait", 2500)]),
    ("photo", "/photo", [("wait", 2500)]),
    ("dashboard", "/dashboard", [("wait", 3500)]),
    ("devis_editeur", "/devis-editeur/{DOC}", [("wait", 3500)]),
    ("devis_suivi", "/devis", [("wait", 3000)]),
    ("clients", "/clients", [("wait", 2500)]),
    ("factures", "/factures", [("wait", 2500)]),
    ("bibliotheque", "/bibliotheque", [("wait", 2500)]),
    ("plan", "/plan?open={PLAN}", [("wait", 7000)]),
    ("appro", "/appro", [("wait", 3000)]),
    ("etudes_pc", "/pc", [("wait", 3000)]),
    ("radar", "/radar", [("wait", 6000)]),
    ("rentabilite", "/rentabilite", [("wait", 3000), ("check", '[data-testid="profit-include-open"]'), ("wait", 1500)]),
    ("suivi_chantier", "/suivi-chantier", [("wait", 3000)]),
    ("equipe", "/equipe", [("wait", 2500)]),
    ("rendu_ia", "/rendu-ia", [("wait", 3000)]),
    ("blog", "/blog", [("wait", 2500)]),
    ("tarifs", "/tarifs", [("wait", 2500)]),
    ("fonctionnalites", "/fonctionnalites", [("wait", 2500)]),
]


async def run():
    os.makedirs(OUT, exist_ok=True)
    ctx_ids = json.loads(os.environ.get("CTX_IDS", "{}"))
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        ctx = await browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1, locale="fr-FR")
        page = await ctx.new_page()
        await page.goto(f"{BASE}/login", wait_until="domcontentloaded")
        await page.wait_for_selector('input[type="email"]', timeout=20000)
        await page.fill('input[type="email"]', EMAIL)
        await page.fill('input[type="password"]', PWD)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(3500)
        # bannière cookies
        try:
            await page.click("text=Tout accepter", timeout=3000)
        except Exception:
            pass
        await page.add_style_tag(content="[data-testid='help-chatbot'], .help-chatbot { display:none !important }")
        for slug, url, actions in SCENES:
            url = url.replace("{DOC}", ctx_ids.get("doc", "")).replace("{PLAN}", ctx_ids.get("plan", ""))
            try:
                await page.goto(BASE + url, wait_until="domcontentloaded")
                await page.wait_for_timeout(1500)
                for kind, arg in actions:
                    try:
                        if kind == "wait":
                            await page.wait_for_timeout(arg)
                        elif kind == "click":
                            await page.click(arg, timeout=8000)
                        elif kind == "check":
                            await page.check(arg, timeout=8000)
                        elif kind == "scroll":
                            await page.locator(arg).scroll_into_view_if_needed(timeout=8000)
                    except Exception as e:  # noqa: BLE001
                        print("  action skipped", slug, kind, arg, type(e).__name__)
                await page.evaluate("document.querySelectorAll('[class*=sonner], [data-sonner-toaster]').forEach(e=>e.remove())")
                await page.screenshot(path=f"{OUT}/{slug}.png", full_page=False)
                print("ok", slug, url)
            except Exception as e:  # noqa: BLE001
                print("FAIL", slug, type(e).__name__, str(e)[:120])
        await browser.close()


asyncio.run(run())
