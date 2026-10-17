"""Auditoria i18n — Playwright navega o preview autenticado e extrai texto visível.
Deteta strings FR restantes filtradas por regex.
Saída: /app/audit/i18n_audit.txt
"""
import re
import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "https://construpilot-recon.preview.emergentagent.com"
EMAIL = os.environ.get("TEST_ADMIN_EMAIL") or "info@construpilot.pt"
PASSWORD = (os.environ.get("TEST_ADMIN_PASSWORD") or "").strip()
if not PASSWORD or PASSWORD == "<redacted>":
    raise SystemExit("TEST_ADMIN_PASSWORD ausente/placeholder no ambiente. Abort.")
OUT_DIR = Path("/app/audit")
OUT_DIR.mkdir(parents=True, exist_ok=True)

PUBLIC = ["/", "/blog", "/comparativo", "/cgv", "/confidentialite"]
AUTH = [
    "/dashboard", "/biblioteca", "/calculadoras", "/photo",
    "/plan-takeoff", "/clients", "/orcamentos", "/faturas",
    "/definicoes", "/conta", "/admin", "/coach",
    "/estimador", "/precos-materiais",
]

FR_REGEX = re.compile(
    r"\b(Créer|Enregistrer|Rechercher|Aucun|Aucune|Supprimer|Modifier|"
    r"Ajouter|Annuler|Fermer|Envoyer|Signer|Nouveau|Nouvelle|Chantier|"
    r"Fournisseur|Étape|Devis|Facture|Ouvrages|Ouvrage|Matériaux|Métré|"
    r"Bienvenue|Photo de la|Précision|Analyser|Confiance|Cloison|Plafond|"
    r"Plancher|Fenêtre|Porte-fenêtre|Douche|Baignoire|Lavabo|Évier|"
    r"Radiateur|Chauffage|Ventilation|Isolation|Peinture|Papier peint|"
    r"Faïence|Parquet|Revêtement|Meuble|Placard|Prise|Interrupteur|"
    r"Éclairage|Luminaire|Robinet|Mitigeur|Chauffe-eau|Ballon|Menuiseries|"
    r"Doublage|Enduit|Ravalement|Zinguerie|Volet|Aujourd'hui|Hier|Demain|"
    r"Semaine|piscine|piscines|Bibliothèque|Votre|Vos ouvrages|Nouvel élément|"
    r"Désignation|Unité|Plomberie|Plâtrerie|Bâtiment|piscine|Rénovation|"
    r"Placoplâtre|Cuvette|Robinetterie|Cloisonnement|Chape|Chantier|"
    r"étanchéité|Étanchéité|Doublage|Fournir|Fournitures)\b"
)


def dismiss_overlays(page):
    for sel in [
        'button:has-text("Aceitar")', 'button:has-text("Accepter")',
        'button:has-text("Saltar")', 'button:has-text("Recusar")',
    ]:
        try:
            page.locator(sel).first.click(timeout=1000)
            page.wait_for_timeout(300)
        except Exception:
            pass


def audit(page, path):
    try:
        page.goto(BASE + path, wait_until="networkidle", timeout=25000)
    except Exception as e:
        return {"path": path, "error": str(e)[:80], "hits": []}
    page.wait_for_timeout(1500)
    dismiss_overlays(page)
    try:
        text = page.evaluate("() => document.body.innerText || ''")
    except Exception:
        text = ""
    title = ""
    try:
        title = page.title()
    except Exception:
        pass

    hits = set()
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or len(line) > 150:
            continue
        if FR_REGEX.search(line):
            # ignorar linhas que são apenas prosa de LLM longa
            hits.add(line)
    return {"path": path, "title": title[:80], "url": page.url, "hits": sorted(hits)}


def main():
    report = OUT_DIR / "i18n_audit.txt"
    with sync_playwright() as p, open(report, "w", encoding="utf-8") as f:
        browser = p.chromium.launch(headless=True, executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1600, "height": 1000})
        page = ctx.new_page()
        # Pré-desligar tour
        page.goto(BASE + "/login", wait_until="networkidle", timeout=25000)
        page.wait_for_timeout(1000)
        page.evaluate("localStorage.setItem('onboarding_skipped','1');"
                      "localStorage.setItem('cookies_accepted','1');")
        # Login
        try:
            page.fill('[data-testid="login-email-input"]', EMAIL)
            page.fill('[data-testid="login-password-input"]', PASSWORD)
            page.locator('button[type="submit"]').first.click()
            page.wait_for_timeout(5000)
            print(f"login → {page.url}")
        except Exception as e:
            print("Login failed:", e)

        all_results = []

        # públicas (não precisam login)
        for path in PUBLIC + AUTH:
            r = audit(page, path)
            all_results.append(r)
            marker = f"[{len(r['hits'])}]" if 'hits' in r else "[ERR]"
            print(f"  {marker:6s} {path:30s} {r.get('title','')[:60]}")

        # relatório
        f.write("=== Auditoria i18n ===\n\n")
        total_hits = 0
        all_strings = set()
        for r in all_results:
            f.write(f"--- {r['path']} ({r.get('url','?')}) ---\n")
            if r.get("error"):
                f.write(f"ERROR: {r['error']}\n\n")
                continue
            f.write(f"Title: {r.get('title','')}\n")
            f.write(f"Hits: {len(r['hits'])}\n")
            for line in r["hits"]:
                f.write(f"  · {line}\n"); all_strings.add(line)
            total_hits += len(r["hits"])
            f.write("\n")

        f.write(f"\n=== TOTAL: {total_hits} hits · {len(all_strings)} strings únicas ===\n")
        for s in sorted(all_strings):
            f.write(f"  ! {s}\n")

        browser.close()
    print(f"\nRelatório: {report}")
    print(f"Total hits: {total_hits} | únicas: {len(all_strings)}")


if __name__ == "__main__":
    main()
