"""Capture les captures d'écran (mode clair) de ConstruPilot pour la vidéo de démo."""
import asyncio
import os
from pathlib import Path
from playwright.async_api import async_playwright

BASE = os.environ.get("PREVIEW_URL", "https://pilot-build-demo.preview.emergentagent.com")
OUT = Path("/app/frontend/public/demo")
OUT.mkdir(parents=True, exist_ok=True)

SHOTS = [
    ("home", "/", 3500, None),
    ("estimation", "/estimation", 3500, None),
    ("metre", "/plan?open=plan_uitest", 5500, None),
    ("calculateurs", "/calculateurs", 3000, None),
    ("escaliers", "/escaliers", 3500, "calc"),
    ("plan", "/plan", 3800, None),
    ("pro", "/pro", 3000, None),
    ("dashboard", "/dashboard", 3800, None),
]


async def light(page):
    await page.evaluate("() => { localStorage.setItem('construpilot_theme','light'); document.documentElement.classList.remove('dark'); }")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path="/usr/bin/google-chrome", args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.goto(f"{BASE}/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)
        await light(page)
        try:
            await page.click('button:has-text("Tout accepter")', timeout=2500)
        except Exception:
            pass
        _email = os.environ.get("DEMO_RECORDER_EMAIL") or "pro@construpilot.fr"
        _pwd = os.environ.get("DEMO_RECORDER_PASSWORD")
        if not _pwd:
            raise SystemExit("DEMO_RECORDER_PASSWORD ausente no ambiente. Abort.")
        await page.fill('input[type="email"]', _email)
        await page.fill('input[type="password"]', _pwd)
        await page.click('button:has-text("Se connecter")')
        await page.wait_for_timeout(4000)
        await light(page)
        for name, url, wait, action in SHOTS:
            try:
                await page.goto(f"{BASE}{url}", wait_until="domcontentloaded")
                await page.wait_for_timeout(1000)
                await light(page)
                await page.wait_for_timeout(wait)
                if action == "calc":
                    try:
                        await page.fill('[data-testid="stair-field-avail-length"]', '5000')
                        await page.fill('[data-testid="stair-field-avail-width"]', '1200')
                        await page.fill('[data-testid="stair-field-stair-width"]', '1000')
                        await page.click('[data-testid="stair-calculate-btn"]')
                        await page.wait_for_timeout(2500)
                    except Exception as e:
                        print("calc err", e)
                await page.evaluate("() => window.scrollTo(0,0)")
                await page.wait_for_timeout(400)
                await page.screenshot(path=str(OUT / f"{name}.png"))
                print("shot", name, "ok", flush=True)
            except Exception as e:
                print("shot", name, "ERR", repr(e)[:120], flush=True)
        await browser.close()
    print("DONE", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
