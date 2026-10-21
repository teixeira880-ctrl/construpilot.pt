import os
from playwright.sync_api import sync_playwright

BASE = "https://pilot-build-demo.preview.emergentagent.com"
OUT = "/app/.media/frames"
os.makedirs(OUT, exist_ok=True)

EXEC = "/root/bin/chromium" if os.path.exists("/root/bin/chromium") else "/usr/bin/google-chrome"


def shot(page, name):
    page.screenshot(path=f"{OUT}/{name}.png", full_page=False)
    print("saved", name)


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=EXEC, args=["--no-sandbox"])
    ctx = browser.new_context(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
    page = ctx.new_page()

    page.goto(f"{BASE}/estimation", wait_until="networkidle")
    page.wait_for_timeout(2500)
    try:
        page.get_by_role("button", name="Tout accepter").click(timeout=4000)
        page.wait_for_timeout(500)
    except Exception:
        pass

    # Step 0
    try:
        page.get_by_test_id("input-city").fill("Nice")
        page.get_by_test_id("input-surface").fill("45")
    except Exception as e:
        print("step0", e)
    page.wait_for_timeout(600)
    shot(page, "01_step0")

    page.get_by_test_id("wizard-next-btn").click()
    page.wait_for_timeout(900)
    try:
        page.get_by_test_id("input-description").fill("Rénovation complète d'une salle de bain")
    except Exception as e:
        print("step1", e)
    page.wait_for_timeout(500)
    shot(page, "02_step1")

    page.get_by_test_id("wizard-next-btn").click()
    page.wait_for_timeout(1000)
    for sel in ["lot-toggle-plomberie", "lot-toggle-carrelage", "lot-toggle-peinture",
                "lot-toggle-electricite", "lot-toggle-salle-de-bain"]:
        try:
            el = page.get_by_test_id(sel)
            if el.count() > 0:
                el.first.click(timeout=1500)
        except Exception:
            pass
    page.wait_for_timeout(500)
    shot(page, "03_step2")

    page.get_by_test_id("wizard-compute-btn").click()
    page.wait_for_timeout(5000)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(500)
    shot(page, "04_result_top")
    # scroll a bit to reveal breakdown/CTA
    page.evaluate("window.scrollBy(0, 500)")
    page.wait_for_timeout(600)
    shot(page, "05_result_mid")

    browser.close()
print("DONE")
