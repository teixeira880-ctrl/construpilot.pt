import os
from playwright.sync_api import sync_playwright

BASE = "https://pilot-build-demo.preview.emergentagent.com"
OUT = "/app/.media/est"
os.makedirs(OUT, exist_ok=True)
EXEC = "/root/bin/chromium" if os.path.exists("/root/bin/chromium") else "/usr/bin/google-chrome"


def shot(page, name):
    page.screenshot(path=f"{OUT}/{name}.png", full_page=False)
    print("saved", name)


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=EXEC, args=["--no-sandbox"])
    ctx = browser.new_context(
        viewport={"width": 414, "height": 896}, device_scale_factor=3,
        is_mobile=True, has_touch=True, service_workers="block",
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                   "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
    ctx.add_init_script("try{localStorage.setItem('cp_pwa_dismissed_at', String(Date.now()));}catch(e){}")
    page = ctx.new_page()

    page.goto(f"{BASE}/estimation", wait_until="networkidle")
    page.wait_for_timeout(2500)
    try:
        page.get_by_role("button", name="Tout accepter").click(timeout=4000)
        page.wait_for_timeout(500)
    except Exception:
        pass

    page.get_by_test_id("input-city").fill("Nice")
    page.get_by_test_id("input-surface").fill("45")
    page.wait_for_timeout(600)
    shot(page, "01_infos")

    page.get_by_test_id("wizard-next-btn").click()
    page.wait_for_timeout(1000)
    try:
        page.get_by_test_id("input-description").fill("Rénovation complète d'une salle de bain")
    except Exception as e:
        print("desc", e)
    page.wait_for_timeout(500)
    shot(page, "02_batiment")

    page.get_by_test_id("wizard-next-btn").click()
    page.wait_for_timeout(1200)
    for sel in ["lot-toggle-plomberie", "lot-toggle-carrelage", "lot-toggle-peinture",
                "lot-toggle-electricite", "lot-toggle-salle-de-bain"]:
        try:
            el = page.get_by_test_id(sel)
            if el.count() > 0:
                el.first.click(timeout=1200)
        except Exception:
            pass
    page.wait_for_timeout(500)
    shot(page, "03_lots")

    page.get_by_test_id("wizard-compute-btn").click()
    page.wait_for_timeout(5500)
    page.evaluate("window.scrollTo(0,0)")
    page.wait_for_timeout(500)
    shot(page, "04_resultat_prix")
    page.evaluate("window.scrollBy(0,560)")
    page.wait_for_timeout(600)
    shot(page, "05_resultat_detail")
    page.evaluate("window.scrollBy(0,560)")
    page.wait_for_timeout(600)
    shot(page, "06_resultat_actions")
    browser.close()
print("DONE")
