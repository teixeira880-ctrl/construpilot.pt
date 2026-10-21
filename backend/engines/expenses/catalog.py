"""Verified application inventory, not a list of assumed AI vendors."""
import os

PROVIDERS = {
    "autodesk": ("Autodesk AutoCAD", "cad", ["APS_CLIENT_ID", "APS_CLIENT_SECRET"], "billing_export_required"),
    "openai_direct": ("OpenAI · direto", "ai", ["OPENAI_API_KEY"], "billing_export_required"),
    "emergent": ("IA · canal Emergent", "ai", ["EMERGENT_LLM_KEY"], "billing_export_required"),
    "runway": ("Runway · imagens / vídeo", "media", ["RUNWAYML_API_SECRET"], "balance_available"),
    "elevenlabs": ("ElevenLabs · voz", "audio", ["ELEVENLABS_API_KEY"], "balance_available"),
    "mercifacteur": ("Merci Facteur", "postal", ["MERCIFACTEUR_PUBLIC_KEY", "MERCIFACTEUR_SECRET_KEY"], "balance_available"),
    "cloudconvert": ("CloudConvert", "cad", ["CLOUDCONVERT_API_KEY"], "billing_export_required"),
    "tavily": ("Tavily · pesquisa", "search", ["TAVILY_API_KEY"], "balance_available"),
    "resend": ("Resend · e-mail", "email", ["RESEND_API_KEY"], "billing_export_required"),
    "babylovegrowth": ("BabyLoveGrowth · SEO", "seo", ["BABYLOVEGROWTH_API_KEY"], "billing_export_required"),
    "facturx": ("Factur-X API", "documents", ["FACTURX_API_KEY"], "billing_export_required"),
    "stripe": ("Stripe · taxas", "payments", ["STRIPE_SECRET_KEY"], "fees_available"),
    "storage": ("Armazenamento externo", "storage", ["INTEGRATION_PROXY_URL"], "billing_export_required"),
    "local_3d": ("3D / vídeo local", "local", [], "local_processing"),
    "public_data": ("SITADEL / dados públicos", "public_data", [], "public_service"),
    "other": ("Outros serviços externos", "other", [], "manual_records"),
}
UNITS = {"calls", "input_tokens", "output_tokens", "cached_input_tokens", "seconds", "images", "videos", "pages", "letters", "conversions", "characters", "bytes", "credits"}


def inventory():
    return [{"provider": key, "name": row[0], "category": row[1],
             "coverage": "observed" if key in {"autodesk", "openai_direct", "emergent", "runway", "mercifacteur", "babylovegrowth"} else "manual",
             "configured": all(bool(os.environ.get(k)) for k in row[2]) if row[2] else None,
             "capability": row[3]} for key, row in PROVIDERS.items()]