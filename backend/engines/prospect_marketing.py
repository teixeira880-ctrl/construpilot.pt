"""E-mails publicitaires pour les nouveaux prospects (français).

Deux cibles, un même objectif : créer un compte gratuit (conversion).
- Particuliers (leads ayant demandé une estimation de travaux).
- Professionnels du BTP (artisans, BET) pas encore clients.

Réutilise l'identité de marque (orange #FF5A00) et le pied de page de `emailer`.
"""
from engines.emailer import BRAND, _footer

# ============ PARTICULIERS (leads) ============

PART_SUBJECT = "Votre projet de travaux mérite le bon prix — et le bon artisan"
PART_PREHEADER = "Estimez gratuitement vos travaux, comparez les prix et trouvez un pro de confiance."

PART_TEXT = """Bonjour,

Vous avez un projet de travaux ? ConstruPilot vous aide à avancer sereinement.

- Estimation gratuite et instantanée : connaissez le coût réaliste de vos travaux.
- Prix justes et transparents : des montants calculés, pas des chiffres au hasard.
- Comparez et décidez : mettez en face plusieurs options en toute clarté.
- Trouvez le bon pro : échangez avec des professionnels près de chez vous.

Créez votre compte gratuit (sans carte bancaire) : {cta_url}

À très vite,
L'équipe ConstruPilot
"""

PART_FEATURES = [
    ("\U0001F4B6", "Estimation gratuite et instantanée",
     "Décrivez votre projet et obtenez une fourchette de prix réaliste en quelques minutes."),
    ("\U0001F50E", "Des prix justes et transparents",
     "Des montants <b>calculés</b>, basés sur des données de marché — jamais des chiffres au hasard."),
    ("\u2696\uFE0F", "Comparez et décidez sereinement",
     "Visualisez clairement vos options et choisissez en toute confiance, sans pression."),
    ("\U0001F477", "Trouvez le bon professionnel",
     "Échangez avec des artisans près de chez vous et avancez sur votre chantier."),
]

# ============ PROFESSIONNELS ============

PRO_SUBJECT = "ConstruPilot — des devis BTP exacts, en une fraction du temps"
PRO_PREHEADER = "Métré de plans, devis déterministes, études de structure et facturation Factur-X. Essai gratuit."

PRO_TEXT = """Bonjour,

ConstruPilot est le copilote des pros du bâtiment : des chiffres exacts, jamais inventés.
Nos calculs sont 100 % déterministes — chaque euro est traçable.

- Métré de plans : importez un plan, mesurez surfaces et longueurs en quelques clics.
- Devis déterministes : montants exacts (zéro hallucination), export PDF prêt pour le client.
- StructuroPilot : études de structure déterministes, sans hypothèse non vérifiée.
- Facturation Factur-X : factures électroniques conformes à la norme EN 16931.

Créez votre compte gratuit (sans carte bancaire) : {cta_url}

À très vite,
L'équipe ConstruPilot
"""

PRO_FEATURES = [
    ("\U0001F4D0", "Métré de plans",
     "Importez un plan PDF ou image, mesurez surfaces, longueurs et quantités à l'échelle. "
     "Le métré alimente directement votre devis."),
    ("\U0001F9EE", "Devis déterministes",
     "Des montants <b>exacts et calculés</b>, jamais inventés par une IA. Chaque ligne traçable, "
     "export PDF propre, prêt pour le client."),
    ("\U0001F3D7\uFE0F", "StructuroPilot — études de structure",
     "Un moteur de calcul <b>déterministe</b> qui bloque toute hypothèse non vérifiée. "
     "Pas d'approximation sur la sécurité."),
    ("\U0001F9FE", "Facturation Factur-X",
     "Générez des factures électroniques conformes à la norme EN 16931, prêtes pour vos clients "
     "et l'administration."),
]


def _feature_rows(features) -> str:
    rows = ""
    for icon, title, desc in features:
        rows += (
            '<tr><td style="padding:14px 0;border-bottom:1px solid #eef1f5">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
            f'<td width="44" valign="top" style="font-size:24px;line-height:28px">{icon}</td>'
            '<td valign="top">'
            f'<div style="font-size:15px;font-weight:700;color:#0A0D14;margin-bottom:3px">{title}</div>'
            f'<div style="font-size:13px;line-height:1.55;color:#475569">{desc}</div>'
            '</td></tr></table></td></tr>'
        )
    return rows


def _build(*, preheader: str, headline: str, intro_html: str, section_label: str,
           features, cta_url: str, cta_label: str, cta_note: str,
           unsubscribe_url: str | None = None) -> str:
    cta_btn = (
        f'<tr><td align="center" style="padding:28px 0 8px">'
        f'<a href="{cta_url}" style="background:{BRAND};color:#fff;text-decoration:none;'
        f'padding:14px 32px;font-family:Arial,sans-serif;font-size:15px;font-weight:bold;'
        f'border-radius:6px;display:inline-block">{cta_label}</a></td></tr>'
        f'<tr><td align="center" style="padding:0 0 4px">'
        f'<span style="font-size:12px;color:#94A3B8">{cta_note}</span></td></tr>'
    )
    return f"""<!doctype html>
<html><body style="margin:0;background:#f5f5f7;font-family:Arial,sans-serif;color:#0A0D14">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">{preheader}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:32px 0">
<tr><td align="center">
<table role="presentation" width="580" cellpadding="0" cellspacing="0"
       style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">
<tr><td style="padding:26px 28px;border-bottom:3px solid {BRAND}">
  <div style="font-size:24px;font-weight:800;letter-spacing:-0.5px">ConstruPilot</div>
  <div style="color:#64748B;font-size:12px;margin-top:4px">Estimez, Comparez, Construisez.</div>
</td></tr>
<tr><td style="padding:30px 28px 8px">
  <h1 style="font-size:22px;margin:0 0 14px 0;line-height:1.3">{headline}</h1>
  <div style="font-size:15px;line-height:1.6;color:#334155">{intro_html}</div>
</td></tr>
<tr><td style="padding:16px 28px 0">
  <div style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;
       color:{BRAND};margin-bottom:4px">{section_label}</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
  {_feature_rows(features)}
  </table>
</td></tr>
<tr><td style="padding:0 28px">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{cta_btn}</table>
</td></tr>
<tr><td style="padding:18px 28px 28px">
  <div style="font-size:13px;line-height:1.6;color:#64748B">
    Une question ? Répondez simplement à cet e-mail, notre équipe vous accompagne.<br/><br/>
    À très vite,<br/><b style="color:#334155">L'équipe ConstruPilot</b>
  </div>
</td></tr>
{_footer(unsubscribe_url)}
</table></td></tr></table></body></html>"""


def prospect_particulier_html(first_name: str | None, cta_url: str,
                              unsubscribe_url: str | None = None) -> str:
    greet = f"Bonjour {first_name}," if first_name else "Bonjour,"
    intro = (
        f'<p style="margin:0 0 12px">{greet}</p>'
        '<p style="margin:0 0 12px">Vous avez un <b>projet de travaux</b> ? '
        'ConstruPilot vous aide à avancer sereinement, du premier chiffrage au bon artisan.</p>'
        '<p style="margin:0">Gratuit, sans engagement, et pensé pour vous donner les '
        '<b>vrais prix</b> — pas des estimations fantaisistes.</p>'
    )
    return _build(
        preheader=PART_PREHEADER, headline=f"Votre projet mérite le bon prix \U0001F3E1",
        intro_html=intro, section_label="Avec ConstruPilot, vous pouvez",
        features=PART_FEATURES, cta_url=cta_url, cta_label="Créer mon compte gratuit",
        cta_note="Gratuit · sans carte bancaire · moins d'une minute",
        unsubscribe_url=unsubscribe_url)


def prospect_pro_html(first_name: str | None, cta_url: str,
                      unsubscribe_url: str | None = None) -> str:
    greet = f"Bonjour {first_name}," if first_name else "Bonjour,"
    intro = (
        f'<p style="margin:0 0 12px">{greet}</p>'
        '<p style="margin:0 0 12px">ConstruPilot est le <b>copilote des pros du bâtiment</b> : '
        'des chiffres <b>exacts</b>, jamais inventés.</p>'
        '<p style="margin:0">Nos calculs sont <b>100 % déterministes</b> — chaque euro est '
        'calculé et traçable. Vous gagnez du temps sans sacrifier la fiabilité.</p>'
    )
    return _build(
        preheader=PRO_PREHEADER, headline="Des devis BTP exacts, en une fraction du temps",
        intro_html=intro, section_label="Ce que ConstruPilot fait pour vous",
        features=PRO_FEATURES, cta_url=cta_url, cta_label="Créer mon compte gratuit",
        cta_note="Essai gratuit · sans carte bancaire · activation immédiate",
        unsubscribe_url=unsubscribe_url)
