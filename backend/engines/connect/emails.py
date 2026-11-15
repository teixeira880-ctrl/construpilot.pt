"""Modelos de e-mail transacionais do Discovery Engine (PT-PT / EN / FR).

Só mensagens transacionais pedidas pelo visitante ou enviadas individualmente por um admin.
Nenhum envio em massa, nenhum documento confidencial anexado, nenhuma reunião inventada:
a confirmação de marcação só existe quando o admin indica a data/hora real.
"""
from __future__ import annotations

from html import escape

BRAND = "#3F7D54"
COPPER = "#B87333"

T = {
    "footer": {
        "pt": "ConstruPilot · construpilot.pt · Recebe este e-mail porque o pediu na nossa página. Para retirar os seus dados, responda a este e-mail.",
        "en": "ConstruPilot · construpilot.pt · You are receiving this e-mail because you requested it on our website. To have your data removed, reply to this e-mail.",
        "fr": "ConstruPilot · construpilot.pt · Vous recevez cet e-mail car vous l'avez demandé sur notre site. Pour supprimer vos données, répondez à cet e-mail.",
    },
    "hello": {"pt": "Olá {name},", "en": "Hello {name},", "fr": "Bonjour {name},"},
    "hello_anon": {"pt": "Olá,", "en": "Hello,", "fr": "Bonjour,"},
    "sign": {"pt": "— Equipa ConstruPilot", "en": "— The ConstruPilot team", "fr": "— L'équipe ConstruPilot"},
}

TEMPLATES = {
    "request_received": {
        "subject": {"pt": "Recebemos o seu pedido — ConstruPilot", "en": "We received your request — ConstruPilot", "fr": "Nous avons reçu votre demande — ConstruPilot"},
        "title": {"pt": "Pedido recebido", "en": "Request received", "fr": "Demande reçue"},
        "body": {
            "pt": "<p>Obrigado pelo seu interesse. Recebemos o seu pedido de <b>{next_step}</b>.</p><p>Um elemento da equipa vai contactá-lo pelo canal que preferiu. Ainda não há nenhuma reunião marcada: proporemos uma data consigo.</p>",
            "en": "<p>Thank you for your interest. We received your request for <b>{next_step}</b>.</p><p>A team member will contact you through your preferred channel. No meeting has been booked yet: we will agree a date with you.</p>",
            "fr": "<p>Merci de votre intérêt. Nous avons bien reçu votre demande de <b>{next_step}</b>.</p><p>Un membre de l'équipe vous contactera par le canal choisi. Aucun rendez-vous n'est encore fixé : nous conviendrons d'une date avec vous.</p>",
        },
        "cta": {"pt": "Rever o meu diagnóstico", "en": "Review my diagnosis", "fr": "Revoir mon diagnostic"},
    },
    "diagnosis_summary": {
        "subject": {"pt": "O seu diagnóstico ConstruPilot", "en": "Your ConstruPilot diagnosis", "fr": "Votre diagnostic ConstruPilot"},
        "title": {"pt": "O resumo do seu diagnóstico", "en": "Your diagnosis summary", "fr": "Le résumé de votre diagnostic"},
        "body": {
            "pt": "<p>Com base nas suas respostas, o seu principal desafio é <b>{challenge}</b>.</p><p>Funcionalidades sugeridas: {capabilities}.</p><p style=\"color:#64748B;font-size:12px\">Este resumo é indicativo e não constitui um parecer técnico.</p>",
            "en": "<p>Based on your answers, your main challenge is <b>{challenge}</b>.</p><p>Suggested features: {capabilities}.</p><p style=\"color:#64748B;font-size:12px\">This summary is indicative and is not a technical opinion.</p>",
            "fr": "<p>D'après vos réponses, votre principal défi est <b>{challenge}</b>.</p><p>Fonctionnalités suggérées : {capabilities}.</p><p style=\"color:#64748B;font-size:12px\">Ce résumé est indicatif et ne constitue pas un avis technique.</p>",
        },
        "cta": {"pt": "Ver a demonstração", "en": "See the demo", "fr": "Voir la démo"},
    },
    "investor_received": {
        "subject": {"pt": "Recebemos o seu interesse — ConstruPilot", "en": "We received your interest — ConstruPilot", "fr": "Nous avons reçu votre intérêt — ConstruPilot"},
        "title": {"pt": "Obrigado pelo seu interesse", "en": "Thank you for your interest", "fr": "Merci de votre intérêt"},
        "body": {
            "pt": "<p>Recebemos o seu interesse em conhecer a ConstruPilot. Os fundadores vão analisar o seu pedido e responder-lhe pessoalmente.</p><p>Documentação confidencial só é partilhada após uma primeira conversa e autorização expressa.</p>",
            "en": "<p>We received your interest in ConstruPilot. The founders will review your request and reply personally.</p><p>Confidential documents are only shared after a first conversation and explicit authorisation.</p>",
            "fr": "<p>Nous avons reçu votre intérêt pour ConstruPilot. Les fondateurs étudieront votre demande et vous répondront personnellement.</p><p>Les documents confidentiels ne sont partagés qu'après un premier échange et une autorisation explicite.</p>",
        },
        "cta": {"pt": "Ver a ConstruPilot em ação", "en": "See ConstruPilot in action", "fr": "Voir ConstruPilot en action"},
    },
    "partner_received": {
        "subject": {"pt": "Proposta de parceria recebida — ConstruPilot", "en": "Partnership enquiry received — ConstruPilot", "fr": "Demande de partenariat reçue — ConstruPilot"},
        "title": {"pt": "Obrigado pela sua proposta", "en": "Thank you for your enquiry", "fr": "Merci pour votre demande"},
        "body": {
            "pt": "<p>Recebemos a sua proposta de parceria. A pessoa responsável pelo desenvolvimento de negócio vai contactá-lo para uma reunião de descoberta.</p><p>As condições de parceria são definidas caso a caso e só depois dessa conversa.</p>",
            "en": "<p>We received your partnership enquiry. Our business development lead will contact you for a discovery meeting.</p><p>Partnership terms are defined case by case, only after that conversation.</p>",
            "fr": "<p>Nous avons reçu votre demande de partenariat. Le responsable du développement commercial vous contactera pour un rendez-vous de découverte.</p><p>Les conditions de partenariat sont définies au cas par cas, après cet échange.</p>",
        },
        "cta": {"pt": "Ver a demonstração", "en": "See the demo", "fr": "Voir la démo"},
    },
    # Enviados manualmente pelo admin, um a um.
    "meeting_confirmation": {
        "subject": {"pt": "Confirmação da nossa reunião — ConstruPilot", "en": "Our meeting is confirmed — ConstruPilot", "fr": "Confirmation de notre rendez-vous — ConstruPilot"},
        "title": {"pt": "Reunião confirmada", "en": "Meeting confirmed", "fr": "Rendez-vous confirmé"},
        "body": {
            "pt": "<p>Confirmamos a nossa reunião para <b>{when}</b>.</p><p>{note}</p>",
            "en": "<p>We confirm our meeting on <b>{when}</b>.</p><p>{note}</p>",
            "fr": "<p>Nous confirmons notre rendez-vous le <b>{when}</b>.</p><p>{note}</p>",
        },
        "cta": None,
    },
    "follow_up": {
        "subject": {"pt": "Na sequência do seu pedido — ConstruPilot", "en": "Following up on your request — ConstruPilot", "fr": "Suite à votre demande — ConstruPilot"},
        "title": {"pt": "Na sequência do seu pedido", "en": "Following up", "fr": "Suite à votre demande"},
        "body": {"pt": "<p>{note}</p>", "en": "<p>{note}</p>", "fr": "<p>{note}</p>"},
        "cta": {"pt": "Rever o meu diagnóstico", "en": "Review my diagnosis", "fr": "Revoir mon diagnostic"},
    },
    "pilot_invite": {
        "subject": {"pt": "Convite para um piloto ConstruPilot", "en": "Invitation to a ConstruPilot pilot", "fr": "Invitation à un pilote ConstruPilot"},
        "title": {"pt": "Vamos testar com um projeto seu?", "en": "Shall we test it on one of your projects?", "fr": "Testons sur l'un de vos projets ?"},
        "body": {
            "pt": "<p>Propomos um piloto com métricas acordadas consigo (tempo por orçamento, quantidades revistas, margens). {note}</p>",
            "en": "<p>We propose a pilot with metrics agreed with you (time per estimate, reviewed quantities, margins). {note}</p>",
            "fr": "<p>Nous proposons un pilote avec des indicateurs convenus ensemble (temps par devis, quantités revues, marges). {note}</p>",
        },
        "cta": None,
    },
    "partner_meeting_invite": {
        "subject": {"pt": "Reunião de parceria — ConstruPilot", "en": "Partnership meeting — ConstruPilot", "fr": "Rendez-vous partenariat — ConstruPilot"},
        "title": {"pt": "Proposta de reunião de descoberta", "en": "Discovery meeting proposal", "fr": "Proposition de rendez-vous de découverte"},
        "body": {"pt": "<p>{note}</p>", "en": "<p>{note}</p>", "fr": "<p>{note}</p>"},
        "cta": None,
    },
}

ADMIN_TEMPLATES = ("meeting_confirmation", "follow_up", "pilot_invite", "partner_meeting_invite")
NEXT_STEP_LABEL = {
    "meeting": {"pt": "reunião", "en": "a meeting", "fr": "rendez-vous"},
    "individual_demo": {"pt": "demonstração individual", "en": "an individual demo", "fr": "démonstration individuelle"},
    "pilot": {"pt": "piloto com um projeto", "en": "a pilot on a project", "fr": "pilote sur un projet"},
    "report": {"pt": "resumo do diagnóstico", "en": "the diagnosis summary", "fr": "résumé du diagnostic"},
}


def _l(lang: str) -> str:
    return lang if lang in ("pt", "en", "fr") else "pt"


def _wrap(lang: str, title: str, body: str, cta_url: str | None, cta_label: str | None) -> str:
    cta = ""
    if cta_url and cta_label:
        cta = (f'<p style="margin:24px 0 8px"><a href="{escape(cta_url, quote=True)}" style="background:{BRAND};color:#fff;'
               f'text-decoration:none;padding:12px 22px;border-radius:8px;font-weight:700;display:inline-block">{escape(cta_label)}</a></p>')
    return (f'<!doctype html><html lang="{_l(lang)}"><body style="margin:0;background:#F6F3EC;font-family:Arial,Helvetica,sans-serif;color:#1A1D20">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:28px 0"><tr><td align="center">'
            f'<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden;border:1px solid #E7E2D6">'
            f'<tr><td style="background:{BRAND};padding:20px 28px;color:#fff;font-size:20px;font-weight:800">ConstruPilot'
            f'<span style="display:block;height:3px;width:44px;background:{COPPER};margin-top:8px"></span></td></tr>'
            f'<tr><td style="padding:28px;font-size:15px;line-height:1.6"><h1 style="font-size:20px;margin:0 0 14px">{escape(title)}</h1>'
            f'{body}{cta}</td></tr>'
            f'<tr><td style="background:#FAF8F3;padding:14px 28px;color:#8A8577;font-size:11px">{escape(T["footer"][_l(lang)])}</td></tr>'
            f'</table></td></tr></table></body></html>')


def render(key: str, lang: str, *, name: str = "", cta_url: str | None = None, **values) -> tuple[str, str]:
    """Devolve (assunto, html). Todos os valores são escapados."""
    tpl = TEMPLATES[key]
    lg = _l(lang)
    safe = {k: escape(str(v or "")) for k, v in values.items()}
    greeting = T["hello"][lg].format(name=escape(name.strip())) if name.strip() else T["hello_anon"][lg]
    body = f"<p>{greeting}</p>" + tpl["body"][lg].format(**{**{"note": "", "when": "", "next_step": "", "challenge": "", "capabilities": ""}, **safe}) \
        + f'<p style="margin-top:20px">{escape(T["sign"][lg])}</p>'
    cta_label = tpl["cta"][lg] if tpl.get("cta") else None
    return tpl["subject"][lg], _wrap(lg, tpl["title"][lg], body, cta_url, cta_label)
