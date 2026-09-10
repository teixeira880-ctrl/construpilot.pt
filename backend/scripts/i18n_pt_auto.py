"""Extrait les libellés français (JSX + catalogue backend) et les traduit en PT-PT via Claude → pt_auto.json."""
import asyncio, glob, json, os, re, sys
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

SRC = "/app/frontend/src"
OUT = f"{SRC}/i18n/pt_auto.json"
SKIP_FILES = ("I18nContext", "pt_auto", "LandingPortugal", "pcTranslations")

TEXT_RE = re.compile(r">\s*([^<>{}]{3,220}?)\s*<")
FRAG_RE = re.compile(r"[>}]\s*([^<>{}]{3,220}?)\s*[<{]")
ATTR_RE = re.compile(r'(?:placeholder|title|aria-label|alt|label|name|desc|description|subtitle|hint|tagline|kicker|over|tooltip|helper)\s*[=:]\s*["“]([^"”{}<>]{3,220})["”]')
TPL_RE = re.compile(r'(?:placeholder|title|aria-label|label|desc|description|subtitle|hint)\s*[=:]\s*\{?\s*"([^"{}<>]{3,220})"')
ARR_RE = re.compile(r'\[\s*"([^"{}<>]{3,160})"\s*,')
TERN_RE = re.compile(r'(?<=[?:,(=])\s*"([^"{}<>`]{3,200})"(?=\s*[,:)\]};])')
CALL_RE = re.compile(r'(?:toast\.(?:success|error|info|message|warning)|setError|setMessage|setMsg|setStatus)\(\s*"([^"{}<>]{3,200})"')
FR_HINT = re.compile(r"[éèêàçùîôâûœÉÈ]|\b(le|la|les|des|du|de|un|une|et|ou|pour|avec|sur|dans|vos|votre|nos|par|au|aux|est|sont|pas)\b", re.I)


def looks_text(s: str) -> bool:
    s = s.strip()
    if len(s) < 3 or not re.search(r"[A-Za-zÀ-ÿ]{3}", s):
        return False
    if re.search(r"[=;{}\[\]]|&&|\|\||^\W+$|^[a-z0-9_./-]+$|className|data-testid|^https?://|\$\{", s):
        return False
    if s.lower() in ("construpilot", "ok", "pdf", "csv", "excel", "stripe", "resend", "id", "url", "api", "html", "dwg", "dxf"):
        return False
    letters = re.sub(r"[^A-Za-zÀ-ÿ]", "", s)
    if len(letters) < 3:
        return False
    return bool(FR_HINT.search(s)) or (" " in s and len(s) > 8) or s[0].isupper()


def extract() -> list[str]:
    found: set[str] = set()
    files = glob.glob(f"{SRC}/pages/*.jsx") + glob.glob(f"{SRC}/components/**/*.jsx", recursive=True)
    for f in files:
        if any(k in f for k in SKIP_FILES):
            continue
        s = open(f, encoding="utf-8").read()
        for rx in (TEXT_RE, FRAG_RE, ATTR_RE, TPL_RE, ARR_RE, TERN_RE, CALL_RE):
            for m in rx.finditer(s):
                t = re.sub(r"\s+", " ", m.group(1)).strip().replace("&amp;", "&").replace("&nbsp;", " ").replace("&rarr;", "→")
                if looks_text(t):
                    found.add(t)
    # Catalogue backend (types de projet, lots, gammes)
    from engines.catalog import PROJECT_TYPES, LOTS
    for p in PROJECT_TYPES:
        found.add(p["name"])
    for l in LOTS:
        found.add(l["name"])
        for t in l.get("tools") or []:
            found.add(t)
        found.add(l["name"] + " : intervention d'un professionnel fortement recommandée.")
    for f in ("/app/backend/engines/estimation.py", "/app/backend/engines/catalog.py", "/app/backend/engines/pool.py",
              "/app/backend/engines/smart_project.py", "/app/backend/routes/estimation_routes.py",
              "/app/backend/engines/calculators.py", "/app/backend/engines/masonry.py", "/app/backend/routes/calculators.py"):
        if os.path.exists(f):
            src = open(f, encoding="utf-8").read()
            for m in re.finditer(r'"([^"\n{}]{3,200})"', src):
                t = m.group(1).strip()
                if looks_text(t) and FR_HINT.search(t):
                    found.add(t)
            for m in re.finditer(r'"(?:label|title|description|help|hint|placeholder|group|category|name)":\s*"([^"\n]{3,200})"', src):
                t = m.group(1).strip()
                if re.search(r"[A-Za-zÀ-ÿ]{3}", t) and not re.match(r"^[a-z0-9_]+$", t):
                    found.add(t)
    for d in ("Facile", "Intermédiaire", "Difficile", "Pro", "Professionnel", "Économique", "Standard", "Premium"):
        found.add(d)
    return sorted(found)


async def translate(strings: list[str], existing: dict) -> dict:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    todo = [s for s in strings if s not in existing]
    print(f"{len(strings)} libellés, {len(todo)} à traduire")
    out = dict(existing)
    B = 60
    for i in range(0, len(todo), B):
        batch = todo[i:i + B]
        chat = LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"], session_id=f"pt-auto-{i}",
                       system_message=("Tu es traducteur professionnel FR → portugais européen (Portugal, pt-PT, jamais brésilien) "
                                       "pour un logiciel BTP (devis, métré, chantiers). Vocabulaire PT-PT du bâtiment : devis=orçamento, "
                                       "chantier=obra, métré=medições, carrelage=azulejo/mosaico, placo=pladur, parpaing=bloco, "
                                       "HT=s/ IVA, TTC=c/ IVA, facture=fatura, situation de travaux=auto de medição, permis de construire=licença de construção, "
                                       "maître d'ouvrage=dono de obra, corps d'état=especialidade, ouvrage=trabalho/artigo, main-d'œuvre=mão de obra. "
                                       "Garde la même longueur approximative, la ponctuation, les majuscules initiales et les symboles (€, m², %, →, ·). "
                                       "Ne traduis pas les noms propres (ConstruPilot, Stripe, Factur-X, DWG, SITADEL, Merci Facteur, BabyLoveGrowth). "
                                       "Réponds UNIQUEMENT en JSON : un objet {\"fr\": \"pt\"} pour chaque entrée, clés strictement identiques.")).with_model("anthropic", "claude-sonnet-4-5-20250929")
        try:
            resp = await chat.send_message(UserMessage(text=json.dumps(batch, ensure_ascii=False)))
            txt = resp.strip()
            txt = txt[txt.find("{"): txt.rfind("}") + 1]
            data = json.loads(txt)
            for k, v in data.items():
                if k in batch and isinstance(v, str) and v.strip():
                    out[k] = v.strip()
            print(f"  batch {i // B + 1}: {len(data)} ok")
        except Exception as e:  # noqa: BLE001
            print("  batch error", type(e).__name__, str(e)[:120])
        json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0, sort_keys=True)
    return out


if __name__ == "__main__":
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    existing = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    strings = extract()
    if "--dry" in sys.argv:
        print(len(strings)); print("\n".join(strings[:80])); sys.exit(0)
    asyncio.run(translate(strings, existing))
    print("done", OUT)
