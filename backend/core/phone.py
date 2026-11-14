"""Telefone obrigatório em todas as contas (14/11, Martinho) — validação de formato, sem SMS.

normalizar("912 345 678", "pt") → "+351912345678" · normalizar("06 12 34 56 78", "fr") → "+33612345678"
normalizar("+44 7700 900123") → "+447700900123" · normalizar("0044 …") → "+44…". Inválido → ValueError.
"""
import re

INDICATIVO = {"pt": "351", "fr": "33", "es": "34", "it": "39", "de": "49", "en": "44"}


def normalizar(valor: str | None, lang: str | None = "pt") -> str:
    s = re.sub(r"[\s.\-()/]", "", str(valor or ""))
    if s.startswith("00"):
        s = "+" + s[2:]
    if s.startswith("+"):
        if re.fullmatch(r"\+\d{8,15}", s):
            return s
        raise ValueError("telefone inválido")
    if not re.fullmatch(r"\d{9,10}", s):
        raise ValueError("telefone inválido")
    lg = str(lang or "pt").lower()[:2]
    cc = INDICATIVO.get(lg, "351")
    if cc == "351" and len(s) == 9:
        return "+351" + s
    if len(s) == 10 and s.startswith("0"):
        return "+" + cc + s[1:]
    if len(s) == 9 and cc != "351":
        return "+" + cc + s
    raise ValueError("telefone inválido")
