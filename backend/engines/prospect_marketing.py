"""E-mails publicitaires pour les nouveaux prospects (français).

Deux cibles, un même objectif : créer un compte gratuit (conversion).
- Particuliers (leads ayant demandé une estimation de travaux).
- Professionnels du BTP (artisans, BET) pas encore clients.

Réutilise l'identité de marque (orange #FF5A00) et le pied de page de `emailer`.
"""
from engines.emailer import BRAND, _footer

# ============ PARTICULIERS (leads) ============

PART_SUBJECT = "O seu projeto de obras merece o preço certo — e o profissional certo"
PART_PREHEADER = "Estime gratuitamente as suas obras, compare preços e encontre um profissional de confiança."

PART_TEXT = "Olá,\n\nTem um projeto de obras? O ConstruPilot ajuda-o a avançar com tranquilidade.\n\n- Estimativa gratuita e instantânea: conheça o custo realista das suas obras.\n- Preços justos e transparentes: montantes calculados, não números ao acaso.\n- Compare e decida: ponha lado a lado várias opções com toda a clareza.\n- Encontre o profissional certo: fale com profissionais perto de si.\n\nCrie a sua conta gratuita (sem cartão bancário): {cta_url}\n\nAté breve,\nA equipa ConstruPilot\n"

PART_FEATURES = [
    ("\U0001F4B6", "Estimativa gratuita e instantânea",
     "Descreva o seu projeto e obtenha um intervalo de preços realista em poucos minutos."),
    ("\U0001F50E", "Preços justos e transparentes",
     "Montantes <b>calculados</b>, baseados em dados de mercado — nunca números ao acaso."),
    ("\u2696\uFE0F", "Compare e decida com tranquilidade",
     "Visualize claramente as suas opções e escolha com toda a confiança, sem pressão."),
    ("\U0001F477", "Encontre o profissional certo",
     "Fale com profissionais perto de si e avance com a sua obra."),
]

# ============ PROFESSIONNELS ============

PRO_SUBJECT = "ConstruPilot — orçamentos de construção exatos, numa fração do tempo"
PRO_PREHEADER = "Medição de plantas, orçamentos determinísticos, estudos de estrutura e faturação eletrónica. Experiência gratuita."

PRO_TEXT = "Olá,\n\nO ConstruPilot é o copiloto dos profissionais da construção: números exatos, nunca inventados.\nOs nossos cálculos são 100 % determinísticos — cada euro é rastreável.\n\n- Medição de plantas: importe uma planta, meça áreas e comprimentos em poucos cliques.\n- Orçamentos determinísticos: montantes exatos (zero alucinações), exportação PDF pronta para o cliente.\n- StructuroPilot: estudos de estrutura determinísticos (Eurocódigos com Anexos Nacionais portugueses), sem hipóteses não verificadas.\n- Faturação eletrónica: faturas estruturadas conformes à norma EN 16931.\n\nCrie a sua conta gratuita (sem cartão bancário): {cta_url}\n\nAté breve,\nA equipa ConstruPilot\n"

PRO_FEATURES = [
    ("\U0001F4D0", "Medição de plantas",
     "Importe uma planta PDF ou imagem, meça áreas, comprimentos e quantidades à escala. A medição alimenta diretamente o seu orçamento."),
    ("\U0001F9EE", "Orçamentos determinísticos",
     "Montantes <b>exatos e calculados</b>, nunca inventados por uma IA. Cada linha rastreável, exportação PDF limpa, pronta para o cliente."),
    ("\U0001F3D7\uFE0F", "StructuroPilot — estudos de estrutura",
     "Um motor de cálculo <b>determinístico</b> que bloqueia qualquer hipótese não verificada. Sem aproximações na segurança."),
    ("\U0001F9FE", "Faturação eletrónica",
     "Gere faturas eletrónicas conformes à norma EN 16931, prontas para os seus clientes e para a administração."),
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
    return f'<!doctype html>\n<html><body style="margin:0;background:#f5f5f7;font-family:Arial,sans-serif;color:#0A0D14">\n<div style="display:none;max-height:0;overflow:hidden;opacity:0">{preheader}</div>\n<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:32px 0">\n<tr><td align="center">\n<table role="presentation" width="580" cellpadding="0" cellspacing="0"\n       style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">\n<tr><td style="padding:26px 28px;border-bottom:3px solid {BRAND}">\n  <div style="font-size:24px;font-weight:800;letter-spacing:-0.5px">ConstruPilot</div>\n  <div style="color:#64748B;font-size:12px;margin-top:4px">Estime, Compare, Construa.</div>\n</td></tr>\n<tr><td style="padding:30px 28px 8px">\n  <h1 style="font-size:22px;margin:0 0 14px 0;line-height:1.3">{headline}</h1>\n  <div style="font-size:15px;line-height:1.6;color:#334155">{intro_html}</div>\n</td></tr>\n<tr><td style="padding:16px 28px 0">\n  <div style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;\n       color:{BRAND};margin-bottom:4px">{section_label}</div>\n  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">\n  {_feature_rows(features)}\n  </table>\n</td></tr>\n<tr><td style="padding:0 28px">\n  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{cta_btn}</table>\n</td></tr>\n<tr><td style="padding:18px 28px 28px">\n  <div style="font-size:13px;line-height:1.6;color:#64748B">\n    Uma pergunta? Responda simplesmente a este e-mail, a nossa equipa acompanha-o.<br/><br/>\n    Até breve,<br/><b style="color:#334155">A equipa ConstruPilot</b>\n  </div>\n</td></tr>\n{_footer(unsubscribe_url)}\n</table></td></tr></table></body></html>'


def prospect_particulier_html(first_name: str | None, cta_url: str,
                              unsubscribe_url: str | None = None) -> str:
    greet = f'Olá {first_name},' if first_name else "Bom dia,"
    intro = (
        f'<p style="margin:0 0 12px">{greet}</p><p style="margin:0 0 12px">Tem um <b>projeto de obras</b>? O ConstruPilot ajuda-o a avançar com tranquilidade, da primeira orçamentação ao profissional certo.</p><p style="margin:0">Gratuito, sem compromisso, e pensado para lhe dar os <b>preços reais</b> — não estimativas fantasiosas.</p>'
    )
    return _build(
        preheader=PART_PREHEADER, headline=f'O seu projeto merece o preço certo 🏡',
        intro_html=intro, section_label="Com o ConstruPilot, pode",
        features=PART_FEATURES, cta_url=cta_url, cta_label="Criar a minha conta gratuita",
        cta_note="Gratuito · sem cartão bancário · menos de um minuto",
        unsubscribe_url=unsubscribe_url)


def prospect_pro_html(first_name: str | None, cta_url: str,
                      unsubscribe_url: str | None = None) -> str:
    greet = f'Olá {first_name},' if first_name else "Bom dia,"
    intro = (
        f'<p style="margin:0 0 12px">{greet}</p><p style="margin:0 0 12px">O ConstruPilot é o <b>copiloto dos profissionais da construção</b>: números <b>exatos</b>, nunca inventados.</p><p style="margin:0">Os nossos cálculos são <b>100 % determinísticos</b> — cada euro é calculado e rastreável. Ganha tempo sem sacrificar a fiabilidade.</p>'
    )
    return _build(
        preheader=PRO_PREHEADER, headline="Orçamentos de construção exatos, numa fração do tempo",
        intro_html=intro, section_label="O que o ConstruPilot faz por si",
        features=PRO_FEATURES, cta_url=cta_url, cta_label="Criar a minha conta gratuita",
        cta_note="Experiência gratuita · sem cartão bancário · ativação imediata",
        unsubscribe_url=unsubscribe_url)
