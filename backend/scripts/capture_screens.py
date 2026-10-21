"""Captures d'écran réelles de ConstruPilot (compte pro connecté) pour les présentations.

python backend/scripts/capture_screens.py
→ backend/assets/screens/*.png
"""
import asyncio
import os

from playwright.async_api import async_playwright

BASE = os.environ["SCREENS_BASE_URL"].rstrip("/")
EMAIL = os.environ["SCREENS_EMAIL"]
PASSWORD = os.environ["SCREENS_PASSWORD"]
OUT = "/app/backend/assets/screens/"

PAGES = [
    ("dashboard", "/dashboard"),
    ("dpgf", "/dpgf"),
    ("devis", "/devis"),
    ("chantiers", "/chantiers"),
    ("situations", "/situations"),
    ("assistant", "/assistant"),
]


async def main():
    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox"])
        page = await browser.new_page(viewport={"width": 1600, "height": 1000})
        await page.goto(f"{BASE}/login", wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)
        for label in ("Tout accepter", "Accept all"):
            btn = page.get_by_role("button", name=label)
            if await btn.count():
                await btn.first.click()
                await page.wait_for_timeout(800)
                break
        await page.fill('[data-testid="login-email-input"]', EMAIL)
        await page.fill('[data-testid="login-password-input"]', PASSWORD)
        await page.click('[data-testid="login-submit-btn"]', force=True)
        await page.wait_for_timeout(9000)
        print("après login :", page.url)
        if "/login" in page.url:
            raise SystemExit("connexion échouée")
        for label in ("Tout accepter", "Accept all"):
            btn = page.get_by_role("button", name=label)
            if await btn.count():
                await btn.first.click()
                break
        await page.add_style_tag(content="[class*='cookie'],[id*='cookie'],[class*='crisp'],"                                         "[id*='crisp'],[data-testid*='help-widget']{display:none!important}")
        for name, path in PAGES:
            await page.goto(f"{BASE}{path}", wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)
            await page.add_style_tag(content="[class*='crisp'],[id*='crisp']{display:none!important}")
            await page.screenshot(path=f"{OUT}{name}.png", full_page=False)
            print(name, path, os.path.getsize(f"{OUT}{name}.png"))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
