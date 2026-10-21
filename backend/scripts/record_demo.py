"""Étape 2 — Enregistre la vidéo en CALANT chaque page sur la durée exacte de sa
narration (lue depuis /tmp/narration.json). Chaque section reste visible au moins le
temps de sa voix off → synchro parfaite. Démonstrations réelles pour métré / devis / factures."""
import asyncio, json, time
from pathlib import Path
from playwright.async_api import async_playwright

BASE = "https://pilot-build-demo.preview.emergentagent.com"
REC = Path("/tmp/rec"); REC.mkdir(parents=True, exist_ok=True)
DURS = {k: v["duration"] for k, v in json.loads(Path("/tmp/narration.json").read_text()).items()}
POST_GAP = 1.1  # marge après la fin de la voix avant de changer de page
CANVAS = '[data-testid=plan-canvas-surface] canvas'  # l'élément <canvas> réel (pas la barre d'outils)

CURSOR = """() => { if (window.__curInit) return; window.__curInit=true;
  const mk=()=>{ if(document.getElementById('__dc'))return;
    const c=document.createElement('div'); c.id='__dc';
    c.style.cssText='position:fixed;top:0;left:0;width:24px;height:24px;z-index:2147483647;pointer-events:none;transition:transform .5s cubic-bezier(.22,.61,.36,1);filter:drop-shadow(0 2px 3px rgba(0,0,0,.4));';
    c.innerHTML='<svg width=24 height=24 viewBox=\"0 0 24 24\"><path d=\"M4 2l6 16 2.6-6.6L19 8.8z\" fill=\"#111\" stroke=\"#fff\" stroke-width=\"1.6\"/></svg>';
    document.body.appendChild(c);
    window.__cur=(x,y)=>{c.style.transform=`translate(${x}px,${y}px)`};
    window.__click=()=>{const m=document.getElementById('__dc');const t=(m.style.transform.match(/translate\\(([-0-9.]+)px,\\s*([-0-9.]+)px\\)/)||[0,0,0]);const x=+t[1],y=+t[2];const r=document.createElement('div');r.style.cssText='position:fixed;width:26px;height:26px;border:3px solid #ff5a00;border-radius:50%;z-index:2147483646;pointer-events:none;transition:all .55s ease-out;left:'+(x-1)+'px;top:'+(y-1)+'px;opacity:.95;';document.body.appendChild(r);requestAnimationFrame(()=>{r.style.transform='scale(2.2)';r.style.opacity='0';});setTimeout(()=>r.remove(),650);};
  };
  if(document.body)mk();else document.addEventListener('DOMContentLoaded',mk);}"""

TOUR = [
    ("home", "/", None),
    ("estimation", "/estimation", "type_estim"),
    ("metre", "/plan", "metre_full"),
    ("plans_pro", "/plans-pro", "scan"),
    ("controle", "/controle-cotes", None),
    ("escaliers", "/escaliers", "stairs3d"),
    ("calculateurs", "/calculateurs", "scan"),
    ("prix", "/prix", None),
    ("devis", "/devis", "scan"),
    ("devis_editeur", "/devis-editeur", "devis_full"),
    ("factures", "/factures", "factures_full"),
    ("situations", "/situations", None),
    ("clients", "/clients", None),
    ("chantiers", "/chantiers", "scan"),
    ("suivi", "/suivi-chantier", None),
    ("dpgf", "/dpgf", "scan"),
    ("analyse_docs", "/analyse-documents", "scan"),
    ("scanner", "/scanner-devis", None),
    ("appro", "/appro", None),
    ("etudes_pc", "/etudes-pc", "scan"),
    ("mesure_photo", "/mesure-photo", None),
    ("rendu_ia", "/rendu-ia", None),
    ("multiniveaux", "/plan", "group"),
    ("bibliotheque", "/bibliotheque", None),
    ("catalogue", "/mon-catalogue", None),
    ("equipe", "/equipe", None),
    ("rh", "/rh", None),
    ("entreprise", "/entreprise", None),
    ("ma_page", "/ma-page", None),
    ("radar", "/radar", None),
    ("assistant", "/assistant", None),
    ("pro", "/pro", "scan"),
    ("dashboard", "/dashboard", "scan"),
]
offsets = {}


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True, executable_path="/usr/bin/google-chrome",
                                    args=["--no-sandbox", "--disable-dev-shm-usage"])
        c0 = await b.new_context(viewport={"width": 1920, "height": 1080})
        pg = await c0.new_page()
        await pg.goto(f"{BASE}/login", wait_until="domcontentloaded"); await pg.wait_for_timeout(1200)
        await pg.evaluate("()=>localStorage.setItem('construpilot_theme','light')")
        try: await pg.click('button:has-text("Tout accepter")', timeout=2500)
        except Exception: pass
        await pg.fill('input[type=email]', 'pro@construpilot.fr')
        await pg.fill('input[type=password]', 'Pro2026!')
        await pg.click('button:has-text("Se connecter")'); await pg.wait_for_timeout(3500)
        state = await c0.storage_state(); await c0.close()

        ctx = await b.new_context(viewport={"width": 1920, "height": 1080}, storage_state=state,
                                  record_video_dir=str(REC), record_video_size={"width": 1920, "height": 1080})
        await ctx.add_init_script(CURSOR)
        page = await ctx.new_page()
        page.set_default_timeout(4500)  # évite les blocages de 30s sur fill/click ratés

        async def safe(coro):
            try: return await coro
            except Exception as e: print("  warn", repr(e)[:80]); return None

        async def light():
            await safe(page.evaluate("()=>{try{localStorage.setItem('construpilot_theme','light');document.documentElement.classList.remove('dark');}catch(e){}}"))

        async def cur(x, y, w=600):
            await safe(page.evaluate(f"window.__cur&&window.__cur({x},{y})")); await page.wait_for_timeout(w)

        async def move_to(sel, w=650):
            try:
                bb = await page.locator(sel).first.bounding_box()
                if bb: await cur(bb["x"]+bb["width"]/2, bb["y"]+bb["height"]/2, w); return bb
            except Exception: pass
            return None

        async def click_sel(sel, w=550):
            await move_to(sel, w); await safe(page.evaluate("window.__click&&window.__click()"))
            try: await page.locator(sel).first.click(timeout=4000)
            except Exception as e: print("  click fail", sel, repr(e)[:50])
            await page.wait_for_timeout(450)

        async def fill_sel(sel, val):
            try: await page.fill(sel, val)
            except Exception as e: print("  fill fail", sel, repr(e)[:50])

        async def set_field(sel, val):
            # saisie robuste pour les inputs numériques contrôlés (React)
            try:
                loc = page.locator(sel).first
                await loc.scroll_into_view_if_needed()
                bb = await loc.bounding_box()
                if bb: await cur(bb["x"]+bb["width"]/2, bb["y"]+bb["height"]/2, 220)
                await loc.click()
                await loc.press("Control+a"); await loc.press("Delete")
                await loc.type(str(val), delay=45)
                await loc.press("Tab")
            except Exception as e: print("  set fail", sel, repr(e)[:50])

        async def cbox():
            try: return await page.locator(CANVAS).first.bounding_box()
            except Exception: return None

        async def canvas_click(bb, fx, fy, w=420):
            if not bb: return
            x, y = bb["x"] + bb["width"] * fx, bb["y"] + bb["height"] * fy
            await cur(x, y, 240); await safe(page.evaluate("window.__click&&window.__click()"))
            await safe(page.mouse.click(x, y)); await page.wait_for_timeout(w)

        async def goto(url):
            await safe(page.goto(f"{BASE}{url}", wait_until="domcontentloaded"))
            await page.wait_for_timeout(1700); await light(); await page.wait_for_timeout(600)

        async def scan():
            await cur(500, 350); await page.mouse.wheel(0, 450); await page.wait_for_timeout(900)
            await cur(1150, 500); await page.mouse.wheel(0, -250); await page.wait_for_timeout(700)

        # ---------- actions ----------
        async def a_type_estim():
            await scan()
            try:
                ta = page.locator('textarea, input[type=text]').first
                bb = await ta.bounding_box()
                if bb:
                    await cur(bb["x"]+50, bb["y"]+bb["height"]/2); await ta.click()
                    await page.keyboard.type("Rénovation appartement 60 m² : peinture, sol, cuisine", delay=35)
            except Exception: pass

        async def a_metre_full():
            # import + nommage
            imported = False
            try:
                await page.wait_for_selector('#plan-upload-input', timeout=25000)
                await page.locator('#plan-upload-input').set_input_files('/tmp/plan_import.png', timeout=20000)
                await page.wait_for_timeout(1500)
                await move_to('[data-testid=pending-file-name-0]')
                await fill_sel('[data-testid=pending-file-name-0]', "Plan RDC — Appartement")
                await page.wait_for_timeout(600)
                await click_sel('[data-testid=plan-import-confirm]')
                await page.wait_for_selector(CANVAS, timeout=15000)
                imported = True
                await page.wait_for_timeout(1500); await light()
            except Exception as e: print("  import", repr(e)[:60])
            if not imported:
                await scan(); return  # import raté → on n'enchaîne pas des échecs
            # calibration (avec une nouvelle tentative si la boîte de dialogue n'apparaît pas)
            calibrated = False
            for attempt in range(2):
                bb = await cbox()
                try:
                    await click_sel('[data-testid=tool-calibrate]'); await page.wait_for_timeout(400)
                    await canvas_click(bb, 0.09, 0.10, 600); await canvas_click(bb, 0.92, 0.10, 600)
                    await page.wait_for_selector('[data-testid=calib-distance-input]', timeout=3000)
                    await page.wait_for_timeout(400)
                    await fill_sel('[data-testid=calib-distance-input]', "8")
                    await click_sel('[data-testid=calib-confirm-btn]'); await page.wait_for_timeout(1600); await light()
                    calibrated = True; break
                except Exception as e:
                    print("  calib try", attempt, repr(e)[:50])
                    await safe(page.keyboard.press("Escape")); await page.wait_for_timeout(500)
            if not calibrated:
                await scan(); return
            # les outils de dessin sont désormais actifs
            try:
                if await page.locator('[data-testid=tool-surface]').is_disabled():
                    await scan(); return
            except Exception:
                await scan(); return
            bb = await cbox()
            # surface (Séjour, haut-gauche)
            try:
                await click_sel('[data-testid=tool-surface]')
                for fx, fy in [(0.11,0.14),(0.45,0.14),(0.45,0.49),(0.11,0.49)]:
                    await canvas_click(bb, fx, fy)
                await click_sel('[data-testid=tool-finish-surface]'); await page.wait_for_timeout(900)
            except Exception as e: print("  surface", repr(e)[:60])
            # périmètre (Cuisine, haut-droit)
            try:
                await click_sel('[data-testid=tool-polyline]')
                for fx, fy in [(0.55,0.14),(0.9,0.14),(0.9,0.49),(0.55,0.49)]:
                    await canvas_click(bb, fx, fy)
                await click_sel('[data-testid=tool-finish-polyline]'); await page.wait_for_timeout(900)
            except Exception as e: print("  poly", repr(e)[:60])
            # distance (linéaire)
            try:
                await click_sel('[data-testid=tool-distance]')
                await canvas_click(bb, 0.11, 0.93); await canvas_click(bb, 0.9, 0.93)
                await click_sel('[data-testid=tool-finish-distance]'); await page.wait_for_timeout(900)
            except Exception as e: print("  dist", repr(e)[:60])
            # pièce + déduction ouverture (Chambre, bas-gauche)
            try:
                bb = await cbox()
                await click_sel('[data-testid=tool-room]'); await page.wait_for_timeout(300)
                for fx, fy in [(0.11,0.56),(0.47,0.56),(0.47,0.9),(0.11,0.9)]:
                    await canvas_click(bb, fx, fy, 500)
                if await page.locator('[data-testid=tool-finish-room]').count():
                    await click_sel('[data-testid=tool-finish-room]'); await page.wait_for_timeout(700)
                    await fill_sel('[data-testid=room-name-input]', "Chambre")
                    await click_sel('[data-testid=room-save-btn]'); await page.wait_for_timeout(900)
                    await click_sel('[data-testid=tool-opening]')
                    await canvas_click(bb, 0.2, 0.9); await canvas_click(bb, 0.32, 0.9)
                    await page.wait_for_timeout(600)
                    if await page.locator('[data-testid=opening-submit-btn]').count():
                        await click_sel('[data-testid=opening-submit-btn]'); await page.wait_for_timeout(900)
            except Exception as e: print("  opening", repr(e)[:60])

        async def a_devis_full():
            await page.wait_for_timeout(600)
            # l'éditeur charge clients + bibliothèque : on attend la 1ère ligne (avec 1 rechargement)
            ready = False
            for attempt in range(2):
                try:
                    await page.wait_for_selector('[data-testid=editor-line-designation-0]', timeout=15000)
                    ready = True; break
                except Exception:
                    print("  editor not ready, reload", attempt)
                    await safe(page.goto(f"{BASE}/devis-editeur", wait_until="domcontentloaded"))
                    await page.wait_for_timeout(1500); await light()
            if not ready:
                await scan(); return
            await page.wait_for_timeout(500)

            async def last_idx():
                return await page.locator('[data-testid^="editor-line-designation-"]').count() - 1

            async def fill_line(i, desig, qty, price):
                await set_field(f'[data-testid=editor-line-designation-{i}]', desig)
                await set_field(f'[data-testid=editor-line-qty-{i}]', qty)
                await set_field(f'[data-testid=editor-line-price-{i}]', price)
                await move_to(f'[data-testid=editor-line-total-{i}]', 500)
                await page.wait_for_timeout(300)

            # Ligne 1 : le devis démarre avec une ligne fourniture vierge → on la remplit
            try:
                await fill_line(0, "Peinture acrylique mate — murs et plafonds", "85", "4.5")
            except Exception as e: print("  line0", repr(e)[:50])
            # Ligne 2 : main d'œuvre (ajout + remplissage de la dernière ligne)
            try:
                await click_sel('[data-testid=editor-add-mainoeuvre]'); await page.wait_for_timeout(500)
                await fill_line(await last_idx(), "Main d'œuvre application peinture", "16", "38")
            except Exception as e: print("  line1", repr(e)[:50])
            # Ligne 3 : fourniture supplémentaire
            try:
                await click_sel('[data-testid=editor-add-fourniture]'); await page.wait_for_timeout(500)
                await fill_line(await last_idx(), "Enduit de lissage + bandes à joint", "45", "6")
            except Exception as e: print("  line2", repr(e)[:50])
            # TVA sur toutes les lignes (recalcul temps réel)
            try:
                await move_to('[data-testid=bulk-vat-select]', 500)
                await page.locator('[data-testid=bulk-vat-select]').first.select_option("10")
                await page.wait_for_timeout(900)
            except Exception as e: print("  vat", repr(e)[:50])
            await move_to('[data-testid=editor-margin-total]', 800)
            await move_to('[data-testid=editor-pdf-btn]', 900)

        async def a_factures_full():
            await scan()
            for sel in ['[data-testid=invoice-from-quote-btn]', '[data-testid=new-invoice-btn]']:
                try:
                    if await page.locator(sel).count():
                        await move_to(sel, 900); await page.wait_for_timeout(400); break
                except Exception: pass

        async def a_stairs3d():
            try:
                await safe(page.wait_for_selector('[data-testid=stair-field-avail-length]', timeout=15000))
                # reculement dispo réaliste → escalier réalisable (défaut 4000 = non réalisable)
                await set_field('[data-testid=stair-field-avail-length]', "5000")
                await page.wait_for_timeout(300)
                await click_sel('[data-testid=stair-calculate-btn]')
                # attendre le VRAI résultat (le calcul déterministe prend ~3-4s)
                await safe(page.wait_for_selector('[data-testid=stair-result-detail]', timeout=12000))
                await page.wait_for_timeout(1200)
                if await page.locator('[data-testid=tab-view3d]').count():
                    await click_sel('[data-testid=tab-view3d]')
                    await safe(page.wait_for_selector('[data-testid=stair-3d] canvas', timeout=6000))
                    await page.wait_for_timeout(1200)
                    cv = await page.locator('[data-testid=stair-3d] canvas').first.bounding_box()
                    if cv:
                        cx, cy = cv["x"]+cv["width"]/2, cv["y"]+cv["height"]/2
                        await cur(cx, cy, 300); await page.mouse.move(cx, cy); await page.mouse.down()
                        for dx in range(0, 240, 20):
                            await page.mouse.move(cx+dx, cy-dx/3); await cur(cx+dx, cy-dx/3, 50)
                        await page.mouse.up()
            except Exception as e: print("  stairs", repr(e)[:60])

        async def a_group():
            try:
                await page.mouse.wheel(0, 700); await page.wait_for_timeout(900)
                if await page.locator('[data-testid=new-plan-group-btn]').count():
                    await click_sel('[data-testid=new-plan-group-btn]'); await page.wait_for_timeout(1200)
                    if await page.locator('[data-testid=group-name-input]').count():
                        await move_to('[data-testid=group-name-input]')
                        await fill_sel('[data-testid=group-name-input]', "Maison Dupont")
                        await page.wait_for_timeout(1000); await page.keyboard.press('Escape')
                else:
                    await scan()
            except Exception as e: print("  group", repr(e)[:60])

        ACT = {"scan": scan, "type_estim": a_type_estim, "metre_full": a_metre_full,
               "devis_full": a_devis_full, "factures_full": a_factures_full, "group": a_group,
               "stairs3d": a_stairs3d}

        await goto("/"); await light(); t0 = time.time()
        for name, url, act in TOUR:
            if name != "home":
                await goto(url)
            start = time.time() - t0
            offsets[name] = round(start, 2); print("MARK", name, offsets[name], flush=True)
            if act:
                await ACT[act]()
            else:
                await cur(600, 380); await cur(1050, 460, 700)
            # cale sur la durée de la narration (au moins)
            d = DURS.get(name, 5.0)
            elapsed = (time.time() - t0) - start
            remaining = (d + POST_GAP) - elapsed
            if remaining > 0:
                await page.wait_for_timeout(int(remaining * 1000))

        await page.wait_for_timeout(1800)
        vid = page.video; await ctx.close(); path = await vid.path(); await b.close()
        Path("/tmp/rec_meta.json").write_text(json.dumps({"video": path, "offsets": offsets}))
        print("RECORDED", path, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
